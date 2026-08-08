from http.server import BaseHTTPRequestHandler
import cgi
import json
import pdfplumber
import io
import re
import html
import urllib.request

# الرابط المباشر لملف الشبكة (قم بتغييره للرابط الفعلي لملف أمانة)
AMANA_PDF_URL = "https://www.amana.sa/path/to/network.pdf" 

class handler(BaseHTTPRequestHandler):
    
    def process_pdf_data(self, file_data):
        extracted_data = []
        with pdfplumber.open(io.BytesIO(file_data)) as pdf:
            first_page_text = pdf.pages[0].extract_text() or ""
            if "أمانة" not in first_page_text and "AMANA" not in first_page_text.upper():
                return {"status": "error", "message": "هذا الملف لا يتبع لشركة أمانة للتأمين."}

            pages_to_scan = min(20, len(pdf.pages)) 
            for i in range(pages_to_scan):
                page = pdf.pages[i]
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        
                        if len(clean_row) >= 5 and clean_row[1] and "المدينة" not in clean_row[1] and "City" not in clean_row[1]:
                            phone_number, lat, lng = "", "", ""
                            
                            for cell in reversed(clean_row):
                                if re.match(r"^\d{2}\.\d{4,}", cell):
                                    if not lat: lat = cell
                                    elif not lng: lng = cell
                                elif cell.replace('-', '').replace(' ', '').isdigit() and len(cell) > 5 and not phone_number:
                                    phone_number = cell

                            ins_class = clean_row[4] if len(clean_row) > 4 else "شامل"
                            category_type = clean_row[5] if len(clean_row) > 5 else "عام"
                            
                            extracted_data.append({
                                "city": html.escape(clean_row[1]),
                                "district": html.escape(clean_row[2]),
                                "name": html.escape(clean_row[3]),
                                "insurance_class": html.escape(ins_class),
                                "category": html.escape(category_type),
                                "phone": html.escape(phone_number),
                                "lat": lat,
                                "lng": lng
                            })
        
        return {"status": "success", "data": extracted_data}

    def do_GET(self):
        if self.path == '/api/fetch-latest':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            try:
                # محاولة تحميل الملف من موقع أمانة
                req = urllib.request.Request(AMANA_PDF_URL, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=8) as response:
                    file_data = response.read()
                
                result = self.process_pdf_data(file_data)
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
                
            except Exception as e:
                # في حال الحظر من موقع أمانة يتم إرجاع خطأ ليتم تفعيل الرفع اليدوي
                response = {
                    "status": "error", 
                    "message": "لا يمكن السحب التلقائي لوجود حماية على الموقع."
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
                
                # تم رفع الحد المسموح به إلى 10 ميجابايت لتجنب رفض ملفات الـ PDF الكبيرة
                if len(file_data) > 10 * 1024 * 1024:
                     error_res = {"status": "error", "message": "حجم الملف كبير جداً (يجب أن يكون أقل من 10 ميجا)."}
                     self.wfile.write(json.dumps(error_res, ensure_ascii=False).encode('utf-8'))
                     return

                try:
                    result = self.process_pdf_data(file_data)
                    self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
                except Exception as e:
                    response = {"status": "error", "message": "ملف تالف أو غير مدعوم."}
                    self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))