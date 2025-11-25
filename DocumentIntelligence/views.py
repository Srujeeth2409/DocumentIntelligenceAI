import os
from django.shortcuts import render
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, JsonResponse
from django.conf import settings
from PIL import Image
import pytesseract
import cv2
import language_tool_python
import shutil
import zipfile
import tempfile
import json
#import mysql.connector as mq
from django.shortcuts import redirect
import psycopg2 as mq

def logout_view(request):
    # clear session fully
    request.session.flush()
    # redirect to index so navbar shows "Get Started"
    return redirect('index')


# helper: save a processed document entry
def save_document_entry(email, file_name=None, file_url=None, document_type=None,
                        confidence=None, extracted_text=None, summarized_text=None,
                        redacted_url=None, pdf_url=None, operation=None, meta=None):
    try:
        sql = """
            INSERT INTO documents
            (email, file_name, file_url, document_type, confidence, extracted_text,
             summarized_text, redacted_url, pdf_url, operation, meta)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """
        cur.execute(sql, (
            email,
            file_name,
            file_url,
            document_type,
            confidence,
            extracted_text,
            summarized_text,
            redacted_url,
            pdf_url,
            operation,
            json.dumps(meta) if meta is not None else None
        ))
        con.commit()
        return True
    except Exception as e:
        print(f"[ERROR] save_document_entry failed: {e}")
        return False


con = mq.connect(host=os.environ.get("DB_HOST"),
        database=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        port=os.environ.get("DB_PORT", 5432))
cur = con.cursor()


def login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        cur.execute("select name,email,password from users where email=%s and password=%s", (email, password))
        row = cur.fetchone()
        if row is None:
            return render(request, 'login.html', {'msg': 'invalid credentials'})
        else:
            name = row[0]
            request.session['is_authenticated'] = True
            request.session['name'] = name
            request.session['email'] = email
            return redirect('dashboard')
    return render(request, "login.html")



def dashboard(request):
    # require login
    email = request.session.get('email')
    name = request.session.get('name')
    if not email:
        return redirect('login')

    # fetch documents for this user
    try:
        cur.execute("SELECT id, file_name, file_url, document_type, confidence, created_at, operation, meta, pdf_url, redacted_url FROM documents WHERE email=%s ORDER BY created_at DESC", (email,))
        rows = cur.fetchall()
        documents = []
        for r in rows:
            doc = {
                'id': r[0],
                'file_name': r[1],
                'file_url': r[2],
                'document_type': r[3],
                'confidence': r[4],
                'created_at': r[5],
                'operation': r[6],
                'meta': json.loads(r[7]) if r[7] else None,
                'pdf_url': r[8],
                'redacted_url': r[9]
            }
            documents.append(doc)
    except Exception as e:
        print(f"[ERROR] fetching documents for dashboard: {e}")
        documents = []

    return render(request, 'dashboard.html', {
        'name': name,
        'email': email,
        'documents': documents
    })

def register(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        password = request.POST.get("password")
        cur.execute("insert into users (name,email,password) values(%s,%s,%s)", (name, email, password))
        con.commit()
        # create session
        request.session['is_authenticated'] = True
        request.session['name'] = name
        request.session['email'] = email
        return redirect('dashboard')
    return render(request, "login.html")


# Import functions from packages
from document_classification.ocr_extraction import (
    extract_text_from_image,
    classify_document_hybrid,
    extract_invoice_fields,
    extract_aadhar_fields,
    extract_pan_fields,
    extract_driving_license_fields,
    extract_voter_id_fields,
    extract_id_card_fields,
    redact_sensitive_information,
    generate_redacted_pdf,
)

from file_conversions.conversions import (
    jpg_to_pdf,
    word_to_pdf,
    ppt_to_pdf,
    excel_to_pdf,
    pdf_to_jpg,
    pdf_to_word,
    pdf_to_ppt,
    pdf_to_excel,
    protect_pdf
)

# Import Transformers for summarization
from transformers import pipeline

# Initialize Base path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Initialize LanguageTool for grammar correction
try:
    tool = language_tool_python.LanguageTool('en-US', remote_server='http://localhost:8081')
    print("[SUCCESS] LanguageTool initialized successfully!")
except Exception as e:
    print(f"[WARNING] LanguageTool initialization failed: {e}")
    tool = None

# Initialize Summarization Pipeline
print("[INFO] Initializing text summarization model...")
try:
    summarizer = pipeline(
        "summarization",
        model="facebook/bart-large-cnn",
        device=-1
    )
    print("[SUCCESS] Summarization model loaded successfully!")
except Exception as e:
    print(f"[WARNING] Summarizer initialization failed: {e}")
    print("[INFO] Summarization features will be disabled")
    summarizer = None


def summarize_text(text, max_length=150, min_length=50):

    if not summarizer:
        print("[WARNING] Summarizer not available, returning original text")
        return text

    if not text or len(text.strip()) < 100:
        print("[INFO] Text too short for summarization, returning original")
        return text

    try:
        text = text.strip()
        max_input_length = 1024 * 4

        if len(text) > max_input_length:
            print(f"[INFO] Text too long ({len(text)} chars), truncating to {max_input_length}")
            text = text[:max_input_length]

        print("[INFO] Generating summary...")
        summary_result = summarizer(
            text,
            max_length=max_length,
            min_length=min_length,
            do_sample=False,
            truncation=True
        )

        summary_text = summary_result[0]['summary_text']
        print(f"[SUCCESS] Summary generated: {len(summary_text)} characters")
        return summary_text

    except Exception as e:
        print(f"[ERROR] Summarization failed: {e}")
        import traceback
        traceback.print_exc()
        return text


def upscale_image_opencv(image_path, scale=2):
    """Upscale image using OpenCV cubic interpolation"""
    try:
        img = cv2.imread(image_path)
        if img is None:
            print(f"[ERROR] Failed to read image: {image_path}")
            return None

        height, width = img.shape[:2]
        new_size = (width * scale, height * scale)
        upscaled_img = cv2.resize(img, new_size, interpolation=cv2.INTER_CUBIC)

        upscaled_img_rgb = cv2.cvtColor(upscaled_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(upscaled_img_rgb)
        return pil_img

    except Exception as e:
        print(f"[ERROR] Image upscaling failed: {e}")
        return None


def index(request):
    return render(request, "index.html")

def ocr_view(request):
    #This is our OCR Functionality
    extracted_text = None
    corrected_text = None
    summarized_text = None
    doc_type = None
    confidence_percentage = None
    original_image_url = None
    original_image_filename = None

    if request.method == "POST" and request.FILES.get("image"):
        uploaded_file = request.FILES["image"]
        fs = FileSystemStorage()
        filename = fs.save(uploaded_file.name, uploaded_file)
        file_path = fs.path(filename)
        original_image_url = fs.url(filename)
        original_image_filename = filename

        try:
            print(f"[INFO] Processing file: {filename}")
            print("=" * 70)

            #  Upscale image for better OCR accuracy
            print("[STEP 1] Upscaling image...")
            upscaled_img = upscale_image_opencv(file_path)

            if upscaled_img is None:
                upscaled_img = Image.open(file_path)
                print("[WARNING] Using original image without upscaling")

            # OCR using PyTesseract
            print("[STEP 2] Extracting text with OCR...")
            extracted_text = pytesseract.image_to_string(upscaled_img)
            print(f"[INFO] Extracted {len(extracted_text)} characters")
            print("\n" + "=" * 70)
            print("EXTRACTED TEXT:")
            print(extracted_text)
            print("=" * 70)

            # Grammar correction
            print("\n[STEP 3] Correcting grammar...")
            if tool:
                try:
                    matches = tool.check(extracted_text)
                    corrected_text = language_tool_python.utils.correct(extracted_text, matches)
                    print(f"[INFO] Applied {len(matches)} corrections")
                except Exception as lang_error:
                    print(f"[WARNING] Grammar correction failed: {lang_error}")
                    corrected_text = extracted_text
            else:
                corrected_text = extracted_text
                print("[INFO] LanguageTool not available, skipping grammar correction")

            # Document Classification
            print("\n[STEP 4] Classifying document type...")
            try:
                doc_type, confidence_score = classify_document_hybrid(corrected_text)
                confidence_percentage = int(confidence_score * 100)
                print(f"[SUCCESS] Classified as: {doc_type} ({confidence_percentage}%)")
            except Exception as class_error:
                print(f"[WARNING] Classification failed: {class_error}")
                doc_type = "Other"
                confidence_percentage = 0

            #  Text Summarization
            print("\n[STEP 5] Generating AI summary...")
            if corrected_text and len(corrected_text.strip()) > 100:
                summarized_text = summarize_text(
                    corrected_text,
                    max_length=150,
                    min_length=50
                )
                print("\n" + "=" * 70)
                print("AI-GENERATED SUMMARY:")
                print(summarized_text)
                print("=" * 70)
            else:
                print("[INFO] Text too short for summarization")
                summarized_text = corrected_text

            print("\n" + "=" * 70)
            print("[SUCCESS] OCR processing completed!")
            print("=" * 70 + "\n")

        except Exception as e:
            print(f"[ERROR] Processing failed: {e}")
            import traceback
            traceback.print_exc()

    # Calculate text statistics for display
    word_count = len(corrected_text.split()) if corrected_text else 0
    char_count = len(corrected_text) if corrected_text else 0
    line_count = len(corrected_text.split('\n')) if corrected_text else 0

    if corrected_text:
        request.session['extracted_text'] = corrected_text
        request.session['document_type'] = doc_type or 'Other'

    email = request.session.get('email')
    if email:
        save_document_entry(
            email=email,
            file_name=original_image_filename,
            file_url=original_image_url,
            document_type=doc_type,
            confidence=confidence_percentage,
            extracted_text=corrected_text,
            summarized_text=summarized_text,
            redacted_url=None,  # none in ocr_view (if you produce one later, update)
            pdf_url=None,
            operation='ocr',
            meta=None
        )
    return render(request, "ocr.html", {
        "extracted_text": corrected_text,
        "summarized_text": summarized_text,
        "document_type": doc_type,
        "confidence": confidence_percentage,
        "word_count": word_count,
        "char_count": char_count,
        "line_count": line_count,
        "original_image_url": original_image_url,
        "original_image_filename": original_image_filename,
    })


def generate_layout(request):

    if request.method == 'POST':
        try:
            extracted_text = request.POST.get('extracted_text', '')
            document_type = request.POST.get('document_type', 'Other')
            layout_type = request.POST.get('layout_type', 'professional')

            if not extracted_text:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No text provided'
                }, status=400)

            print(f"[INFO] Generating {layout_type} layout for {document_type}")

            html_content = generate_custom_layout(extracted_text, document_type, layout_type)

            return JsonResponse({
                'status': 'success',
                'html_content': html_content,
                'layout_type': layout_type
            })

        except Exception as e:
            print(f"[ERROR] Layout generation error: {e}")
            import traceback
            traceback.print_exc()

            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    }, status=400)


def generate_custom_layout(text, doc_type, layout_type):

    text = text.strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    if layout_type == 'professional':
        return f"""
        <div class="custom-layout-wrapper">
            <div style="font-family: 'Georgia', serif; max-width: 800px; margin: 0 auto; padding: 40px; background: white; box-shadow: 0 0 20px rgba(0,0,0,0.1);">
                <div style="border-bottom: 3px solid #0066cc; padding-bottom: 20px; margin-bottom: 30px;">
                    <h1 style="color: #1a1a1a; font-size: 2.5rem; margin: 0; font-family: 'Georgia', serif;">{doc_type}</h1>
                    <p style="color: #666; margin-top: 10px; font-size: 0.9rem; font-family: 'Georgia', serif;">Professional Document Layout</p>
                </div>
                <div style="line-height: 1.8; color: #333; font-size: 1.1rem; font-family: 'Georgia', serif;">
                    {'<br>'.join(lines)}
                </div>
                <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0; text-align: center; color: #888; font-size: 0.85rem; font-family: 'Georgia', serif;">
                    Generated by Document Intelligence AI
                </div>
            </div>
        </div>
        """

    elif layout_type == 'modern':
        return f"""
        <div class="custom-layout-wrapper">
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 0 auto; padding: 0;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 60px 40px; color: white; border-radius: 12px 12px 0 0;">
                    <h1 style="margin: 0; font-size: 2.8rem; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">{doc_type}</h1>
                    <p style="margin-top: 15px; font-size: 1.1rem; opacity: 0.9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">Modern & Clean Design</p>
                </div>
                <div style="background: white; padding: 40px; border-radius: 0 0 12px 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
                    <div style="line-height: 1.9; color: #1a1a1a; font-size: 1.05rem; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
                        {'<br><br>'.join(lines)}
                    </div>
                </div>
            </div>
        </div>
        """

    elif layout_type == 'minimalist':
        return f"""
        <div class="custom-layout-wrapper">
            <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 700px; margin: 0 auto; padding: 60px 20px;">
                <h1 style="font-size: 2rem; font-weight: 300; color: #1a1a1a; margin-bottom: 10px; letter-spacing: -0.5px; font-family: 'Helvetica Neue', Arial, sans-serif;">{doc_type}</h1>
                <div style="width: 60px; height: 2px; background: #1a1a1a; margin-bottom: 40px;"></div>
                <div style="line-height: 2; color: #333; font-size: 1rem; font-weight: 300; font-family: 'Helvetica Neue', Arial, sans-serif;">
                    {'<br><br>'.join(lines)}
                </div>
            </div>
        </div>
        """

    # Default fallback
    return f"""
    <div class="custom-layout-wrapper">
        <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px; background: white;">
            <h1 style="color: #1a1a1a; margin-bottom: 20px; font-family: Arial, sans-serif;">{doc_type}</h1>
            <div style="line-height: 1.8; color: #333; font-family: Arial, sans-serif;">
                {'<br>'.join(lines)}
            </div>
        </div>
    </div>
    """


def generate_redacted_image(request):

    if request.method == 'POST':
        try:
            filename = request.POST.get('filename')
            doc_type = request.POST.get('document_type')

            if not filename or not doc_type:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Missing filename or document type'
                }, status=400)

            fs = FileSystemStorage()
            file_path = fs.path(filename)

            if not os.path.exists(file_path):
                return JsonResponse({
                    'status': 'error',
                    'message': 'Original image file not found'
                }, status=404)

            print(f"[INFO] Generating redacted image for {doc_type}")
            print("=" * 70)

            redacted_path = redact_sensitive_information(file_path, doc_type)

            if redacted_path and os.path.exists(redacted_path):
                redacted_filename = os.path.basename(redacted_path)
                redacted_url = fs.url(redacted_filename)

                print(f"[SUCCESS] Redacted image created: {redacted_url}")
                print("=" * 70)

                return JsonResponse({
                    'status': 'success',
                    'redacted_url': redacted_url,
                    'redacted_filename': redacted_filename
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to generate redacted image'
                }, status=500)

        except Exception as e:
            print(f"[ERROR] Redaction error: {e}")
            import traceback
            traceback.print_exc()

            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    }, status=400)


def classification(request):
    email = request.session.get('email')
    """Main document classification pipeline"""
    if request.method == 'POST' and request.FILES.get('document'):
        try:
            uploaded_file = request.FILES['document']
            fs = FileSystemStorage()
            filename = fs.save(uploaded_file.name, uploaded_file)
            file_path = fs.path(filename)

            print("=" * 70)
            print(f"[INFO] Processing document: {filename}")
            print("=" * 70)

            # STEP 1: OCR extraction
            print("\n[STEP 1] Extracting text from image...")
            extracted_text = extract_text_from_image(file_path)
            print(f"[INFO] Extracted {len(extracted_text)} characters")
            print("\n" + "=" * 70)
            print("EXTRACTED TEXT:")
            print(extracted_text)
            print("=" * 70)

            # STEP 2: Text Summarization
            print("\n[STEP 2] Generating text summary...")
            summarized_text = None
            if extracted_text and len(extracted_text.strip()) > 100:
                summarized_text = summarize_text(
                    extracted_text,
                    max_length=200,
                    min_length=60
                )
                print("\n" + "=" * 70)
                print("SUMMARIZED TEXT:")
                print(summarized_text)
                print("=" * 70)
            else:
                print("[INFO] Text too short for summarization")

            # STEP 3: Document Classification
            print("\n[STEP 3] Classifying document...")
            doc_type, confidence_score = classify_document_hybrid(extracted_text)
            confidence_percentage = int(confidence_score * 100)
            print(f"[SUCCESS] Classified as: {doc_type} ({confidence_percentage}%)")

            # STEP 4: Image redaction (only for sensitive documents)
            print("\n[STEP 4] Checking if redaction needed...")
            redacted_url = None
            pdf_url = None
            redacted_path = None

            sensitive_docs = ["Aadhar Card", "PAN Card", "Driving License", "Voter ID", "ID Card"]
            if doc_type in sensitive_docs:
                print(f"[INFO] Applying redaction for {doc_type}...")
                redacted_path = redact_sensitive_information(file_path, doc_type)
            else:
                print(f"[INFO] No redaction needed for {doc_type}")

            # STEP 5: Extract fields WITH REDACTION
            print("\n[STEP 5] Extracting document fields...")
            extracted_fields = {}

            if doc_type == "Aadhar Card":
                print("[INFO] Processing Aadhar Card...")
                aadhar_fields_raw = extract_aadhar_fields(extracted_text, redact=False)
                print("RAW Aadhar fields:", aadhar_fields_raw)

                aadhar_fields = extract_aadhar_fields(extracted_text, redact=True)
                print("REDACTED Aadhar fields:", aadhar_fields)

                extracted_fields = {
                    'Aadhar Number': aadhar_fields.get('Aadhar_Number'),
                    'Name': aadhar_fields.get('Name'),
                    'Date of Birth': aadhar_fields.get('DOB'),
                    'Address': aadhar_fields.get('Address')
                }

            elif doc_type == "PAN Card":
                print("[INFO] Processing PAN Card...")
                pan_fields_raw = extract_pan_fields(extracted_text, redact=False)
                print("RAW PAN fields:", pan_fields_raw)

                pan_fields = extract_pan_fields(extracted_text, redact=True)
                print("REDACTED PAN fields:", pan_fields)

                extracted_fields = {
                    'PAN Number': pan_fields.get('PAN_Number'),
                    'Name': pan_fields.get('Name'),
                    "Father's Name": pan_fields.get('Father_Name'),
                    'Date of Birth': pan_fields.get('DOB')
                }

            elif doc_type == "Invoice":
                print("[INFO] Processing Invoice...")
                invoice_fields_raw = extract_invoice_fields(extracted_text, redact=False)
                print("RAW Invoice fields:", invoice_fields_raw)

                invoice_fields = extract_invoice_fields(extracted_text, redact=True)
                print("REDACTED Invoice fields:", invoice_fields)

                extracted_fields = {
                    'Invoice Number': invoice_fields.get('Invoice_Number'),
                    'Date': invoice_fields.get('Date'),
                    'GST Number': invoice_fields.get('GST_Number'),
                    'Total Amount': invoice_fields.get('Total_Amount')
                }

            elif doc_type == "Driving License":
                print("[INFO] Processing Driving License...")
                dl_fields_raw = extract_driving_license_fields(extracted_text, redact=False)
                print("RAW DL fields:", dl_fields_raw)

                dl_fields = extract_driving_license_fields(extracted_text, redact=True)
                print("REDACTED DL fields:", dl_fields)

                extracted_fields = {
                    'DL Number': dl_fields.get('DL_Number'),
                    'Name': dl_fields.get('Name'),
                    'DOB': dl_fields.get('DOB'),
                    'Issue Date': dl_fields.get('Issue_Date'),
                    'Expiry Date': dl_fields.get('Expiry_Date'),
                    'Blood Group': dl_fields.get('Blood_Group'),
                    'Address': dl_fields.get('Address')
                }

            elif doc_type == "Voter ID":
                print("[INFO] Processing Voter ID...")
                voter_fields_raw = extract_voter_id_fields(extracted_text, redact=False)
                print("RAW Voter ID fields:", voter_fields_raw)

                voter_fields = extract_voter_id_fields(extracted_text, redact=True)
                print("REDACTED Voter ID fields:", voter_fields)

                extracted_fields = {
                    'Voter ID': voter_fields.get('Voter_ID'),
                    'Name': voter_fields.get('Name'),
                    "Father's Name": voter_fields.get('Father_Name'),
                    'DOB': voter_fields.get('DOB'),
                    'Address': voter_fields.get('Address')
                }

            elif doc_type == "ID Card":
                print("[INFO] Processing ID Card...")
                id_fields_raw = extract_id_card_fields(extracted_text, redact=False)
                print("RAW ID Card fields:", id_fields_raw)

                id_fields = extract_id_card_fields(extracted_text, redact=True)
                print("REDACTED ID Card fields:", id_fields)

                extracted_fields = {
                    'ID Number': id_fields.get('ID_Number'),
                    'Name': id_fields.get('Name'),
                    'DOB': id_fields.get('DOB'),
                    'Designation': id_fields.get('Designation'),
                    'Department': id_fields.get('Department'),
                    'Organization': id_fields.get('Organization'),
                    'Issue Date': id_fields.get('Issue_Date'),
                    'Expiry Date': id_fields.get('Expiry_Date')
                }

            # STEP 6: Generate redacted image URL and PDF report
            print("\n[STEP 6] Generating outputs...")
            if redacted_path and os.path.exists(redacted_path):
                redacted_filename = os.path.basename(redacted_path)
                redacted_url = fs.url(redacted_filename)
                print(f"[SUCCESS] Redacted image URL: {redacted_url}")

                # Generate PDF with redacted image and fields
                try:
                    pdf_path = generate_redacted_pdf(redacted_path, extracted_fields, doc_type)

                    if pdf_path and os.path.exists(pdf_path):
                        pdf_filename = os.path.basename(pdf_path)
                        pdf_media_path = os.path.join(fs.location, pdf_filename)
                        shutil.copy(pdf_path, pdf_media_path)
                        pdf_url = fs.url(pdf_filename)
                        print(f"[SUCCESS] PDF generated: {pdf_url}")
                    else:
                        print("[ERROR] PDF generation failed: File not created")

                except Exception as pdf_error:
                    print(f"[ERROR] PDF generation error: {pdf_error}")
                    import traceback
                    traceback.print_exc()

            print("\n" + "=" * 70)
            print("[SUCCESS] Document processing completed!")
            print("=" * 70 + "\n")

            return render(request, 'classification.html', {
                'status': 'success',
                'file_name': uploaded_file.name,
                'file_url': fs.url(filename),
                'redacted_url': redacted_url,
                'pdf_url': pdf_url,
                'extracted_text': extracted_text,
                'summarized_text': summarized_text,
                'document_type': doc_type,
                'confidence': confidence_percentage,
                'extracted_fields': extracted_fields
            })


        except Exception as e:
            print(f"\n[ERROR] Main processing error: {e}")
            import traceback
            traceback.print_exc()

            return render(request, 'classification.html', {
                'status': 'error',
                'message': f'Error: {str(e)}'
            })


    if email:
        meta = 'extracted_fields' if 'extracted_fields' else None
        save_document_entry(
            email='email',
            file_name='uploaded_file.name',
            file_url='fs.url(filename)',
            document_type='doc_type',
            confidence='confidence_percentage',
            extracted_text='extracted_text',
            summarized_text='summarized_text',
            redacted_url='redacted_url',
            pdf_url='pdf_url',
            operation='classification',
            meta=meta
        )
    return render(request, 'classification.html', {'status': None})


def convert(request):
    context = {}

    if request.method == "POST":
        target_format = request.POST.get("target_format")
        if target_format == "merge":
            files = request.FILES.getlist("files")  # Get multiple files

            if not files or len(files) < 2:
                context["status"] = "error"
                context["message"] = "Please upload at least 2 PDF files to merge"
                return render(request, "convert.html", context)

            try:
                # Save all uploaded files
                fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, "uploads"))
                input_paths = []

                for uploaded_file in files:
                    filename = fs.save(uploaded_file.name, uploaded_file)
                    input_path = os.path.join(fs.location, filename)
                    input_paths.append(input_path)
                    print(f"[INFO] Saved: {filename}")

                # Prepare output folder
                output_folder = os.path.join(settings.MEDIA_ROOT, "converted")
                os.makedirs(output_folder, exist_ok=True)

                # Create output filename
                output_filename = "merged.pdf"
                output_path = os.path.join(output_folder, output_filename)

                # Merge PDFs
                from file_conversions.conversions import merge_pdfs
                success = merge_pdfs(input_paths, output_path)

                if success and os.path.exists(output_path):
                    print(f"[SUCCESS] Merged PDF ready: {output_path}")

                    # Clean up uploaded files
                    for path in input_paths:
                        try:
                            os.remove(path)
                        except:
                            pass

                    return FileResponse(
                        open(output_path, "rb"),
                        as_attachment=True,
                        filename=output_filename,
                        content_type='application/pdf'
                    )
                else:
                    context["status"] = "error"
                    context["message"] = "Failed to merge PDF files"
                    print("[ERROR] Merge failed")
                    return render(request, "convert.html", context)

            except Exception as e:
                context["status"] = "error"
                context["message"] = f"Error merging PDFs: {str(e)}"
                print(f"[ERROR] PDF merge failed: {e}")
                import traceback
                traceback.print_exc()
                return render(request, "convert.html", context)

        # ------------------- PASSWORD PROTECT PDF -------------------
        if target_format == "protect":
            if not request.FILES.get("file"):
                context["status"] = "error"
                context["message"] = "Please upload a PDF file"
                return render(request, "convert.html", context)

            uploaded_file = request.FILES["file"]
            pdf_password = request.POST.get("pdf_password")

            if not pdf_password:
                context["status"] = "error"
                context["message"] = "Please provide a password"
                return render(request, "convert.html", context)

            try:
                # Save uploaded file
                fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, "uploads"))
                filename = fs.save(uploaded_file.name, uploaded_file)
                input_path = os.path.join(fs.location, filename)

                # Prepare output folder
                output_folder = os.path.join(settings.MEDIA_ROOT, "converted")
                os.makedirs(output_folder, exist_ok=True)

                base_name = os.path.splitext(filename)[0]
                output_path = os.path.join(output_folder, f"{base_name}_protected.pdf")

                # Protect PDF with password
                protect_pdf(input_path, output_path, pdf_password)

                if os.path.exists(output_path):
                    print(f"[SUCCESS] PDF protected: {output_path}")
                    return FileResponse(
                        open(output_path, "rb"),
                        as_attachment=True,
                        filename=f"{base_name}_protected.pdf",
                    )

            except Exception as e:
                context["status"] = "error"
                context["message"] = f"Error protecting PDF: {str(e)}"
                print(f"[ERROR] PDF protection failed: {e}")
                import traceback
                traceback.print_exc()
                return render(request, "convert.html", context)

        # ------------------- REGULAR FILE CONVERSIONS -------------------
        elif request.FILES.get("file"):
            uploaded_file = request.FILES["file"]

            # Save uploaded file
            fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, "uploads"))
            filename = fs.save(uploaded_file.name, uploaded_file)
            input_path = os.path.join(fs.location, filename)

            # Prepare output folder
            output_folder = os.path.join(settings.MEDIA_ROOT, "converted")
            os.makedirs(output_folder, exist_ok=True)

            base_name = os.path.splitext(filename)[0]

            try:
                ext = uploaded_file.name.split(".")[-1].lower()
                print(f"[INFO] Converting {ext} to {target_format}")

                # ------------------- TO PDF -------------------
                if target_format == "pdf":
                    output_path = os.path.join(output_folder, f"{base_name}_converted.pdf")

                    if ext in ["jpg", "jpeg", "png"]:
                        jpg_to_pdf(input_path, output_path)
                    elif ext in ["doc", "docx"]:
                        word_to_pdf(input_path, output_path)
                    elif ext in ["ppt", "pptx"]:
                        ppt_to_pdf(input_path, output_path)
                    elif ext in ["xls", "xlsx"]:
                        excel_to_pdf(input_path, output_path)

                    if os.path.exists(output_path):
                        print(f"[SUCCESS] Converted to PDF: {output_path}")
                        return FileResponse(
                            open(output_path, "rb"),
                            as_attachment=True,
                            filename=os.path.basename(output_path),
                        )

                # ------------------- FROM PDF -------------------
                elif ext == "pdf":
                    if target_format == "jpg":
                        temp_dir = tempfile.mkdtemp()
                        jpg_files = pdf_to_jpg(input_path, temp_dir)

                        zip_filename = f"{base_name}_images.zip"
                        zip_path = os.path.join(output_folder, zip_filename)
                        with zipfile.ZipFile(zip_path, "w") as zipf:
                            for jpg in jpg_files:
                                zipf.write(jpg, os.path.basename(jpg))

                        if os.path.exists(zip_path):
                            print(f"[SUCCESS] Converted to JPG (ZIP): {zip_path}")
                            return FileResponse(
                                open(zip_path, "rb"),
                                as_attachment=True,
                                filename=zip_filename,
                            )

                    elif target_format == "word":
                        output_path = os.path.join(output_folder, f"{base_name}.docx")
                        pdf_to_word(input_path, output_path)

                    elif target_format == "ppt":
                        output_path = os.path.join(output_folder, f"{base_name}.pptx")
                        pdf_to_ppt(input_path, output_path)

                    elif target_format == "excel":
                        output_path = os.path.join(output_folder, f"{base_name}.xlsx")
                        pdf_to_excel(input_path, output_path)

                    if os.path.exists(output_path):
                        print(f"[SUCCESS] Converted from PDF: {output_path}")
                        return FileResponse(
                            open(output_path, "rb"),
                            as_attachment=True,
                            filename=os.path.basename(output_path),
                        )

                else:
                    context["status"] = "error"
                    context["message"] = f"Unsupported file type: {ext}"
                    print(f"[ERROR] {context['message']}")

            except Exception as e:
                context["status"] = "error"
                context["message"] = str(e)
                print(f"[ERROR] Conversion failed: {e}")
                import traceback
                traceback.print_exc()

    return render(request, "convert.html", context)