from http.server import BaseHTTPRequestHandler
import cgi
import json
import pdfplumber
import io
import re
import html
import urllib.request

# الرابط التقريبي (سيتم إرجاع خطأ الحماية ليفعل الرفع اليدوي كما هو مطلوب)
AMANA_PDF_URL = "https://www.amana.sa/" 

class handler(BaseHTTPRequestHandler):
    
    def process_pdf_data(self, file_data):
        extracted_data = []
        with pdfplumber.open(io.BytesIO(file_data)) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            if "أمانة" not in first_page_text and "AMANA" not in first_page_text.upper():
                return {"status": "error", "message": "هذا الملف لا يتبع لشركة أمانة للتأمين. يرجى التأكد من الملف."}

            pages_to_scan = min(30, len(pdf.pages)) 
            for i in range(pages_to_scan):
                page = pdf.pages[i]
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        # تنظيف الخلايا من المسافات والفراغات
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        
                        # التأكد أن الصف ليس صف عناوين وأنه يحتوي على بيانات صحيحة
                        if len(clean_row) >= 6 and clean_row[1] and "المدينة" not in clean_row[1] and "City" not in clean_row[1]:
                            
                            phone_number = ""
                            hospital_type = ""
                            
                            # استخراج رقم الهاتف والنوع من الأعمدة الأخيرة
                            for cell in reversed(clean_row):
                                # البحث عن رقم هاتف
                                if cell.replace('-', '').replace(' ', '').isdigit() and len(cell) > 5 and not phone_number:
                                    phone_number = cell
                                # البحث عن تصنيف المستشفى (MOH أو Private)
                                if "MOH" in cell.upper():
                                    hospital_type = "MOH"
                                elif "PRIVATE" in cell.upper() or "خاص" in cell:
                                    hospital_type = "Private"

                            # تحديد الاسم العربي (عادة يكون في العمود 3 أو 4 بناءً على هيكل ملف أمانة)
                            # الخوارزمية تفحص الأعمدة 3 و 4 وتأخذ النص الذي يحتوي على حروف عربية
                            hospital_name = clean_row[3]
                            if len(clean_row) > 4 and re.search(r'[\u0600-\u06FF]', clean_row[4]):
                                hospital_name = clean_row[4]

                            ins_class = clean_row[-1] if len(clean_row) > 6 else "شامل"
                            category_type = clean_row[5] if len(clean_row) > 5 else "عام"
                            
                            extracted_data.append({
                                "city": html.escape(clean_row[1]),
                                "district": html.escape(clean_row[2]),
                                "name": html.escape(hospital_name),
                                "insurance_class": html.escape(ins_class),
                                "category": html.escape(category_type),
                                "phone": html.escape(phone_number),
                                "type": html.escape(hospital_type) # يحدد إذا كان حكومي أو خاص
                            })
        
        return {"status": "success", "data": extracted_data}

    def do_GET(self):
        if self.path == '/api/fetch-latest':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # إرجاع خطأ متعمد لتشغيل نافذة "يوجد خطأ يمنع سحب البيانات" مع الرابط
            response = {
                "status": "error", 
                "message": "Protection active"
            }
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
                
                if len(file_data) > 10 * 1024 * 1024:
                     error_res = {"status": "error", "message": "حجم الملف كبير جداً."}
                     self.wfile.write(json.dumps(error_res, ensure_ascii=False).encode('utf-8'))
                     return

                try:
                    result = self.process_pdf_data(file_data)
                    self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
                except Exception as e:
                    response = {"status": "error", "message": "ملف تالف أو غير مدعوم."}
                    self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))