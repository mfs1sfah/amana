from http.server import BaseHTTPRequestHandler
import cgi
import json
import pdfplumber
import io
import re
import html

class handler(BaseHTTPRequestHandler):
    
    def process_pdf_data(self, file_data):
        extracted_data = []
        with pdfplumber.open(io.BytesIO(file_data)) as pdf:
            # التحقق من أن الملف لأمانة
            first_page_text = pdf.pages[0].extract_text() or ""
            if "أمانة" not in first_page_text and "AMANA" not in first_page_text.upper():
                return {"status": "error", "message": "هذا الملف لا يتبع لشركة أمانة للتأمين. يرجى التأكد من الملف."}

            # تحديد أول 25 صفحة لتجنب انقطاع الاتصال (Timeout) في سيرفر Vercel المجاني
            pages_to_scan = min(25, len(pdf.pages)) 
            for i in range(pages_to_scan):
                page = pdf.pages[i]
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        # تنظيف الخلايا
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        
                        if len(clean_row) >= 5 and clean_row[1] and "المدينة" not in clean_row[1] and "City" not in clean_row[1]:
                            
                            phone_number = ""
                            hospital_type = "Private" # افتراضي
                            hospital_name = clean_row[3] # الاسم الافتراضي
                            
                            # البحث عن رقم الهاتف ونوع المستشفى
                            for cell in reversed(clean_row):
                                if cell.replace('-', '').replace(' ', '').isdigit() and len(cell) > 5 and not phone_number:
                                    phone_number = cell
                                if "MOH" in cell.upper() or "وزارة" in cell or "حكومي" in cell:
                                    hospital_type = "MOH"

                            # استخراج الاسم العربي: نبحث في الأعمدة عن نص يحتوي حروف عربية
                            for cell in clean_row[2:5]:
                                if re.search(r'[\u0600-\u06FF]', cell):
                                    # إذا كان الخلية تحتوي عربي وانجليزي، نفصلهم ونأخذ العربي
                                    arabic_parts = re.findall(r'[\u0600-\u06FF\s]+', cell)
                                    if arabic_parts:
                                        hospital_name = " ".join(arabic_parts).strip()
                                        break

                            ins_class = clean_row[-1] if len(clean_row) > 6 else "شامل"
                            category_type = clean_row[5] if len(clean_row) > 5 else "عام"
                            
                            extracted_data.append({
                                "city": html.escape(clean_row[1]),
                                "district": html.escape(clean_row[2]),
                                "name": html.escape(hospital_name),
                                "insurance_class": html.escape(ins_class),
                                "category": html.escape(category_type),
                                "phone": html.escape(phone_number),
                                "type": html.escape(hospital_type)
                            })
        
        return {"status": "success", "data": extracted_data}

    def do_GET(self):
        if self.path == '/api/fetch-latest':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # إرجاع خطأ ليفعل رسالة "يوجد خطأ يمنع سحب البيانات"
            response = { "status": "error", "message": "Protection active" }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

    def do_POST(self):
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
                
                try:
                    result = self.process_pdf_data(file_data)
                    self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
                except Exception as e:
                    response = {"status": "error", "message": "فشل الاتصال بالخادم أو الملف تالف."}
                    self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))