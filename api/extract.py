from http.server import BaseHTTPRequestHandler
import cgi
import json
import io
import re
import html
import PyPDF2 

class handler(BaseHTTPRequestHandler):
    
    def process_pdf_data(self, file_data):
        extracted_data = []
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_data))
            
            first_page_text = pdf_reader.pages[0].extract_text() or ""
            if "أمانة" not in first_page_text and "AMANA" not in first_page_text.upper():
                return {"status": "error", "message": "هذا الملف لا يخص شركة أمانة للتأمين."}

            scan_limit = min(60, len(pdf_reader.pages))
            for page_num in range(scan_limit):
                page_text = pdf_reader.pages[page_num].extract_text()
                if not page_text:
                    continue
                    
                lines = page_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if len(line) < 15 or "تعديل قائمة" in line or "City" in line or "المدينة" in line:
                        continue
                    
                    phone_number = ""
                    hospital_type = "خاص"
                    
                    phone_match = re.search(r'(01[1-9]|05|9200)\d{7}', line.replace(' ', '').replace('-', ''))
                    if phone_match:
                        phone_number = phone_match.group(0)
                        
                    if "MOH" in line.upper() or "وزارة" in line or "حكومي" in line:
                        hospital_type = "حكومي"

                    arabic_words = re.findall(r'[\u0600-\u06FF]+', line)
                    if len(arabic_words) >= 3:
                        city = arabic_words[0]
                        district = arabic_words[1]
                        hosp_name = " ".join(arabic_words[2:])
                        
                        if len(hosp_name) < 5 or "تأمين" in hosp_name or "الشركة" == hosp_name:
                            continue
                            
                        ins_class = "شامل"
                        class_match = re.search(r'\b(VIP|A|B|C|D)\b', line.upper())
                        if class_match:
                            ins_class = class_match.group(0)

                        extracted_data.append({
                            "city": html.escape(city),
                            "district": html.escape(district),
                            "name": html.escape(hosp_name),
                            "insurance_class": html.escape(ins_class),
                            "category": "مستشفى / مركز طبي",
                            "phone": html.escape(phone_number),
                            "type": html.escape(hospital_type)
                        })

            if not extracted_data:
                return {"status": "error", "message": "تمت قراءة الملف ولكن لم يتم التعرف على الجداول."}
                
            return {"status": "success", "data": extracted_data}
            
        except Exception as e:
            return {"status": "error", "message": f"حدث خطأ أثناء المعالجة: {str(e)}"}

    def do_POST(self):
        """مسار الرفع اليدوي"""
        if self.path == '/api/extract':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            ctype, pdict = cgi.parse_header(self.headers.get('content-type'))
            pdict['boundary'] = bytes(pdict['boundary'], "utf-8")
            
            if ctype == 'multipart/form-data':
                fields = cgi.parse_multipart(self.rfile, pdict)
                file_data = fields.get('file')[0]
                
                if len(file_data) > 20 * 1024 * 1024:
                     error_res = {"status": "error", "message": "حجم الملف كبير جداً (الحد الأقصى 20 ميجا)."}
                     self.wfile.write(json.dumps(error_res, ensure_ascii=False).encode('utf-8'))
                     return

                try:
                    result = self.process_pdf_data(file_data)
                    self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
                except Exception as e:
                    res = {"status": "error", "message": "فشل قراءة الملف المرفوع."}
                    self.wfile.write(json.dumps(res, ensure_ascii=False).encode('utf-8'))