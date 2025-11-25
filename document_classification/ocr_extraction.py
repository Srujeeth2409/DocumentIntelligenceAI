import pytesseract
from PIL import Image
import cv2
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Image as RLImage, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from PIL import Image as PILImage


def extract_text_from_image(image_path):
    """Extract text from image using Tesseract OCR"""
    img = Image.open(image_path).convert("RGB")
    text = pytesseract.image_to_string(img)
    return text


def mask_sensitive_data(value, data_type):
    """Mask sensitive information in extracted fields"""
    if not value:
        return None

    if data_type == 'aadhar':
        if len(value) >= 4:
            if ' ' in value:
                parts = value.split()
                return f"XXXX XXXX {parts[-1]}"
            else:
                return f"XXXXXXXX{value[-4:]}"
        return "XXXX XXXX XXXX"

    elif data_type == 'pan':
        if len(value) == 10:
            return f"{value[:3]}XX{value[5:9]}X"
        return "XXXXX1234X"

    elif data_type == 'dl':
        if len(value) >= 8:
            return f"{value[:4]}{'X' * (len(value) - 8)}{value[-4:]}"
        return "DLXXXXXXXXXX"

    elif data_type == 'voter_id':
        if len(value) >= 6:
            return f"{value[:3]}{'*' * (len(value) - 6)}{value[-3:]}"
        return "XXX*****XXX"

    elif data_type == 'id_card':
        if len(value) >= 6:
            return f"{'*' * (len(value) - 4)}{value[-4:]}"
        return "ID******"

    elif data_type == 'name':
        parts = value.split()
        if len(parts) > 1:
            return f"{parts[0]} {'*' * len(parts[-1])}"
        return value

    elif data_type == 'dob':
        if '/' in value:
            parts = value.split('/')
            return f"XX/XX/{parts[-1]}"
        elif '-' in value:
            parts = value.split('-')
            return f"XX-XX-{parts[-1]}"
        return "XX/XX/XXXX"

    elif data_type == 'gst':
        if len(value) >= 5:
            return f"{value[:2]}{'*' * (len(value) - 5)}{value[-3:]}"
        return "XXXXXXXXXXXXXXX"

    elif data_type == 'amount':
        return "₹****"

    elif data_type == 'address':
        parts = [p.strip() for p in value.split(',')]
        if len(parts) > 1:
            return f"***, {parts[-1]}"
        return "***"

    else:
        return '*' * len(value)


def classify_document_hybrid(text):
    """Hybrid classification using keyword matching and regex patterns"""
    text_lower = text.lower()

    aadhar_keywords = ["aadhaar", "aadhar", "uidai", "unique identification"]
    pan_keywords = ["pan", "permanent account number", "income tax"]
    invoice_keywords = ["invoice", "bill", "gst", "gstin", "tax invoice"]
    driving_license_keywords = ["driving license", "dl", "driving licence", "licence number"]
    id_card_keywords = ["id card", "identification card", "identity card", "employee id"]
    voter_id_keywords = ["voter id", "elector", "electoral", "voter identification", "epic"]

    aadhar_score = sum(1 for keyword in aadhar_keywords if keyword in text_lower)
    pan_score = sum(1 for keyword in pan_keywords if keyword in text_lower)
    invoice_score = sum(1 for keyword in invoice_keywords if keyword in text_lower)
    dl_score = sum(1 for kw in driving_license_keywords if kw in text_lower)
    id_card_score = sum(1 for kw in id_card_keywords if kw in text_lower)
    voter_id_score = sum(1 for kw in voter_id_keywords if kw in text_lower)

    # Add weight for regex pattern matches
    if re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", text):
        pan_score += 10
    if re.search(r"\b(\d{4}\s\d{4}\s\d{4}|\d{12})\b", text):
        aadhar_score += 10
    if re.search(r"\b[A-Z]{2}[-\s]?\d{2}[-\s]?\d{4}[-\s]?\d{7}\b", text):
        dl_score += 10
    if re.search(r"\b[A-Z]{3}\d{7}\b", text):
        voter_id_score += 10
    if re.search(r"\b(?:ID|EMP|STU)\d{6,}\b", text, re.IGNORECASE):
        id_card_score += 10

    scores = {
        "Aadhar Card": aadhar_score,
        "PAN Card": pan_score,
        "Invoice": invoice_score,
        "Driving License": dl_score,
        "ID Card": id_card_score,
        "Voter ID": voter_id_score
    }

    doc_type = max(scores, key=scores.get)
    confidence = scores[doc_type] / max(sum(scores.values()), 1)

    return doc_type, confidence


def classify_document_with_transformer(text):
    """Wrapper for compatibility - calls hybrid classifier"""
    return classify_document_hybrid(text)


def extract_aadhar_fields(text, redact=False):
    """Extract Aadhaar fields with strong regex for broken spacing"""
    text_cleaned = text.replace("O", "0").replace("o", "0")
    text_cleaned = re.sub(r'[^A-Za-z0-9\s:/\-]', '', text_cleaned)

    aadhar_no_match = re.search(r'\b(?:\d\s?){12}\b', text_cleaned)
    dob_match = re.search(r'\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.](0?[1-9]|1[012])[\/\-\.](19|20)\d\d\b', text_cleaned)

    name = None
    address = None
    lines = text_cleaned.split("\n")

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if "name" in line_lower and "father" not in line_lower:
            if ":" in line:
                name_part = line.split(":", 1)[1].strip()
                if name_part and len(name_part) > 2:
                    name = name_part
            elif i + 1 < len(lines):
                possible_name = lines[i + 1].strip()
                if len(possible_name) > 2 and not any(char.isdigit() for char in possible_name):
                    name = possible_name
            break

    if not name:
        for line in lines[:8]:
            if len(line.strip()) > 4 and len(line.strip()) < 40 and all(
                    c.isalpha() or c.isspace() for c in line.strip()):
                name = line.strip().title()
                break

    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["address", "s/o", "c/o", "d/o"]):
            parts = [lines[j].strip() for j in range(i, min(i + 3, len(lines))) if lines[j].strip()]
            address = ", ".join(parts)
            break

    aadhar_no = aadhar_no_match.group(0) if aadhar_no_match else None
    if aadhar_no:
        aadhar_no = re.sub(r'\s+', ' ', aadhar_no).strip()

    dob = dob_match.group(0) if dob_match else None

    if redact:
        aadhar_no = mask_sensitive_data(aadhar_no, "aadhar")
        name = mask_sensitive_data(name, "name")
        dob = mask_sensitive_data(dob, "dob")
        address = mask_sensitive_data(address, "address")

    return {
        "Aadhar_Number": aadhar_no,
        "Name": name,
        "DOB": dob,
        "Address": address,
    }


def extract_pan_fields(text, redact=False):
    """Extract PAN fields"""
    pan_match = re.search(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", text)
    dob_match = re.search(r"\b(0?[1-9]|[12][0-9]|3[01])[/\-\.](0?[1-9]|1[012])[/\-\.](19|20)\d\d\b", text)

    name = None
    father_name = None
    lines = text.split("\n")

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if "name" in line_lower and "father" not in line_lower:
            name = lines[i + 1].strip() if i + 1 < len(lines) else None
        if "father" in line_lower:
            father_name = lines[i + 1].strip() if i + 1 < len(lines) else None

    pan_no = pan_match.group(0) if pan_match else None
    dob = dob_match.group(0) if dob_match else None

    if redact:
        pan_no = mask_sensitive_data(pan_no, "pan")
        name = mask_sensitive_data(name, "name")
        father_name = mask_sensitive_data(father_name, "name")
        dob = mask_sensitive_data(dob, "dob")

    return {"PAN_Number": pan_no, "Name": name, "Father_Name": father_name, "DOB": dob}


def extract_invoice_fields(text, redact=False):
    """Extract Invoice fields"""
    invoice_no_match = re.search(r"(?:invoice|bill)\s*(?:no|#)?\s*:?\s*([A-Z0-9\-\/]+)", text, re.IGNORECASE)
    total_match = re.search(r"(?:total)\s*:?\s*[\$₹]?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)", text, re.IGNORECASE)
    date_match = re.search(r"(?:date)\s*:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})", text, re.IGNORECASE)
    gst_match = re.search(r"(?:gst|gstin)\s*:?\s*([A-Z0-9]{15})", text, re.IGNORECASE)

    invoice_no = invoice_no_match.group(1) if invoice_no_match else None
    total = total_match.group(1) if total_match else None
    date = date_match.group(1) if date_match else None
    gst = gst_match.group(1) if gst_match else None

    if redact:
        gst = mask_sensitive_data(gst, "gst")
        total = mask_sensitive_data(total, "amount")

    return {
        "Invoice_Number": invoice_no,
        "Total_Amount": total,
        "Date": date,
        "GST_Number": gst,
        "Company_Name": None,
    }


def extract_driving_license_fields(text, redact=False):
    """Extract Driving License fields"""
    text_cleaned = re.sub(r'[^A-Za-z0-9\s:/\-]', '', text)

    dl_match = re.search(r'\b[A-Z]{2}[-\s]?\d{2}[-\s]?\d{4}[-\s]?\d{7}\b', text_cleaned, re.IGNORECASE)
    if not dl_match:
        dl_match = re.search(r'\bDL\d{13,15}\b', text_cleaned, re.IGNORECASE)

    dob_match = re.search(r'\b(0?[1-9]|[12][0-9]|3[01])[/\-\.](0?[1-9]|1[012])[/\-\.](19|20)\d\d\b', text_cleaned)
    issue_date_match = re.search(r'(?:issue|doi)\s*:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', text_cleaned,
                                 re.IGNORECASE)
    expiry_match = re.search(
        r'(?:valid|validity|expiry|exp)\s*(?:till|upto|until)?\s*:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        text_cleaned, re.IGNORECASE)
    blood_group_match = re.search(r'\b(A|B|AB|O)[+-]\b', text)

    name = None
    address = None
    lines = text_cleaned.split("\n")

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()

        if "name" in line_lower and "father" not in line_lower:
            if ":" in line:
                name_part = line.split(":", 1)[1].strip()
                if name_part and len(name_part) > 2:
                    name = name_part
            elif i + 1 < len(lines):
                possible_name = lines[i + 1].strip()
                if len(possible_name) > 2 and not any(char.isdigit() for char in possible_name):
                    name = possible_name

        if "address" in line_lower or "s/o" in line_lower or "c/o" in line_lower:
            parts = [lines[j].strip() for j in range(i, min(i + 3, len(lines))) if lines[j].strip()]
            address = ", ".join(parts[:3])

    if not name:
        for line in lines[:8]:
            if len(line.strip()) > 4 and len(line.strip()) < 40 and all(
                    c.isalpha() or c.isspace() for c in line.strip()):
                name = line.strip().title()
                break

    dl_number = dl_match.group(0) if dl_match else None
    if dl_number:
        dl_number = re.sub(r'\s+', '', dl_number)

    dob = dob_match.group(0) if dob_match else None
    issue_date = issue_date_match.group(1) if issue_date_match else None
    expiry_date = expiry_match.group(1) if expiry_match else None
    blood_group = blood_group_match.group(0) if blood_group_match else None

    if redact:
        dl_number = mask_sensitive_data(dl_number, 'dl')
        name = mask_sensitive_data(name, 'name')
        dob = mask_sensitive_data(dob, 'dob')
        address = mask_sensitive_data(address, 'address')

    return {
        "DL_Number": dl_number,
        "Name": name,
        "DOB": dob,
        "Issue_Date": issue_date,
        "Expiry_Date": expiry_date,
        "Blood_Group": blood_group,
        "Address": address
    }


def extract_voter_id_fields(text, redact=False):
    """Extract Voter ID (EPIC) fields"""
    text_cleaned = re.sub(r'[^A-Za-z0-9\s:/\-]', '', text)

    voter_id_match = re.search(r'\b[A-Z]{3}\d{7}\b', text_cleaned)
    if not voter_id_match:
        voter_id_match = re.search(r'\b[A-Z]{3}[/\-]?\d{7}\b', text_cleaned)

    dob_match = re.search(r'\b(0?[1-9]|[12][0-9]|3[01])[/\-\.](0?[1-9]|1[012])[/\-\.](19|20)\d\d\b', text_cleaned)

    name = None
    father_name = None
    address = None
    lines = text_cleaned.split("\n")

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()

        if "name" in line_lower and "father" not in line_lower and "husband" not in line_lower:
            if ":" in line:
                name_part = line.split(":", 1)[1].strip()
                if name_part and len(name_part) > 2:
                    name = name_part
            elif i + 1 < len(lines):
                possible_name = lines[i + 1].strip()
                if len(possible_name) > 2 and not any(char.isdigit() for char in possible_name):
                    name = possible_name

        if ("father" in line_lower or "husband" in line_lower) and i + 1 < len(lines):
            if ":" in line:
                father_part = line.split(":", 1)[1].strip()
                if father_part and len(father_part) > 2:
                    father_name = father_part
            else:
                possible_father = lines[i + 1].strip()
                if len(possible_father) > 2 and all(c.isalpha() or c.isspace() for c in possible_father):
                    father_name = possible_father

        if "address" in line_lower:
            parts = [lines[j].strip() for j in range(i, min(i + 3, len(lines))) if lines[j].strip()]
            address = ", ".join(parts[:3])

    if not name:
        for line in lines[:8]:
            if len(line.strip()) > 4 and len(line.strip()) < 40 and all(
                    c.isalpha() or c.isspace() for c in line.strip()):
                name = line.strip().title()
                break

    voter_id = voter_id_match.group(0) if voter_id_match else None
    dob = dob_match.group(0) if dob_match else None

    if redact:
        voter_id = mask_sensitive_data(voter_id, 'voter_id')
        name = mask_sensitive_data(name, 'name')
        father_name = mask_sensitive_data(father_name, 'name')
        dob = mask_sensitive_data(dob, 'dob')
        address = mask_sensitive_data(address, 'address')

    return {
        "Voter_ID": voter_id,
        "Name": name,
        "Father_Name": father_name,
        "DOB": dob,
        "Address": address
    }


def extract_id_card_fields(text, redact=False):
    """Extract generic ID Card fields"""
    text_cleaned = re.sub(r'[^A-Za-z0-9\s:/\-]', '', text)

    id_match = re.search(r'\b(?:ID|EMP|STU|CARD)[-\s]?[A-Z0-9]{4,12}\b', text_cleaned, re.IGNORECASE)
    if not id_match:
        id_match = re.search(r'\b\d{6,10}\b', text_cleaned)

    dob_match = re.search(r'\b(0?[1-9]|[12][0-9]|3[01])[/\-\.](0?[1-9]|1[012])[/\-\.](19|20)\d\d\b', text_cleaned)
    issue_date_match = re.search(r'(?:issue|issued)\s*(?:date|on)?\s*:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
                                 text_cleaned, re.IGNORECASE)
    expiry_match = re.search(
        r'(?:valid|validity|expiry|exp)\s*(?:till|upto)?\s*:?\s*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})', text_cleaned,
        re.IGNORECASE)

    name = None
    designation = None
    department = None
    organization = None
    lines = text_cleaned.split("\n")

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()

        if "name" in line_lower and "company" not in line_lower:
            if ":" in line:
                name_part = line.split(":", 1)[1].strip()
                if name_part and len(name_part) > 2:
                    name = name_part
            elif i + 1 < len(lines):
                possible_name = lines[i + 1].strip()
                if len(possible_name) > 2 and not any(char.isdigit() for char in possible_name):
                    name = possible_name

        if "designation" in line_lower or "position" in line_lower:
            if ":" in line:
                designation = line.split(":", 1)[1].strip()
            elif i + 1 < len(lines):
                designation = lines[i + 1].strip()

        if "department" in line_lower or "dept" in line_lower:
            if ":" in line:
                department = line.split(":", 1)[1].strip()
            elif i + 1 < len(lines):
                department = lines[i + 1].strip()

        if ("company" in line_lower or "organization" in line_lower or
                "institute" in line_lower or "university" in line_lower):
            if ":" in line:
                organization = line.split(":", 1)[1].strip()
            else:
                organization = line.strip()

    if not name:
        for line in lines[:8]:
            if len(line.strip()) > 4 and len(line.strip()) < 40 and all(
                    c.isalpha() or c.isspace() for c in line.strip()):
                name = line.strip().title()
                break

    id_number = id_match.group(0) if id_match else None
    dob = dob_match.group(0) if dob_match else None
    issue_date = issue_date_match.group(1) if issue_date_match else None
    expiry_date = expiry_match.group(1) if expiry_match else None

    if redact:
        id_number = mask_sensitive_data(id_number, 'id_card')
        name = mask_sensitive_data(name, 'name')
        dob = mask_sensitive_data(dob, 'dob')

    return {
        "ID_Number": id_number,
        "Name": name,
        "DOB": dob,
        "Designation": designation,
        "Department": department,
        "Organization": organization,
        "Issue_Date": issue_date,
        "Expiry_Date": expiry_date
    }


def redact_sensitive_information(image_path, doc_type):
    """Redact image with black boxes"""
    img = cv2.imread(image_path)
    if img is None:
        return None

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    if doc_type == "Aadhar Card":
        patterns_to_redact = [
            r'\b\d{4}\s\d{4}\s\d{4}\b',
            r'(?:\d\s?){12}',
            r'\b\d{12}\b',
            r'\b[0-9O]{4}\s?[0-9O]{4}\s?[0-9O]{4}\b'
        ]
        keywords_to_redact = ["uid", "aadhaar", "unique", "identification", "name", "address", "s/o", "c/o"]

    elif doc_type == "PAN Card":
        patterns_to_redact = [r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"]
        keywords_to_redact = ["name", "father"]

    elif doc_type == "Invoice":
        patterns_to_redact = [r"\b[A-Z0-9]{15}\b", r"\b\d+(?:,\d{3})*(?:\.\d{2})?\b"]
        keywords_to_redact = ["gstin", "total"]

    elif doc_type == "Driving License":
        patterns_to_redact = [
            r'\b[A-Z]{2}[-\s]?\d{2}[-\s]?\d{4}[-\s]?\d{7}\b',
            r'\bDL\d{13,15}\b'
        ]
        keywords_to_redact = ["name", "address", "s/o", "c/o", "dl", "license"]

    elif doc_type == "Voter ID":
        patterns_to_redact = [r'\b[A-Z]{3}\d{7}\b']
        keywords_to_redact = ["name", "father", "husband", "address", "epic", "voter"]

    elif doc_type == "ID Card":
        patterns_to_redact = [
            r'\b(?:ID|EMP|STU)[-\s]?[A-Z0-9]{4,12}\b',
            r'\b\d{6,10}\b'
        ]
        keywords_to_redact = ["name", "employee", "id", "designation"]

    else:
        patterns_to_redact, keywords_to_redact = [], []

    for i in range(len(data["text"])):
        text = data["text"][i]
        if not text.strip() or int(data["conf"][i]) < 30:
            continue

        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]

        if any(re.search(p, text, re.IGNORECASE) for p in patterns_to_redact) or any(
                k in text.lower() for k in keywords_to_redact
        ):
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 0), -1)

    base_name = image_path.rsplit(".", 1)[0]
    redacted_path = f"{base_name}_redacted.jpg"
    cv2.imwrite(redacted_path, img)
    return redacted_path


def generate_redacted_pdf(redacted_image_path, extracted_fields, doc_type, output_path=None):
    """Generate PDF with redacted image and masked fields"""
    if not output_path:
        base_name = redacted_image_path.rsplit(".", 1)[0]
        output_path = f"{base_name}_report.pdf"

    doc = SimpleDocTemplate(output_path, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1f2937"),
        alignment=1,
    )

    story.append(Paragraph("<b>Redacted Document Report</b>", title_style))
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph(f"<b>Document Type:</b> {doc_type}", styles["Normal"]))
    story.append(Spacer(1, 0.3 * inch))

    try:
        rl_img = RLImage(redacted_image_path, width=6 * inch, height=4 * inch)
        story.append(rl_img)
        story.append(Spacer(1, 0.3 * inch))
    except Exception as e:
        story.append(Paragraph(f"<i>Error loading image: {e}</i>", styles["Normal"]))

    story.append(Paragraph("<b>Extracted Information (Redacted)</b>", styles["Heading2"]))
    story.append(Spacer(1, 0.2 * inch))

    table_data = [["Field", "Value"]]
    for k, v in extracted_fields.items():
        table_data.append([k, str(v) if v else "Not found"])

    table = Table(table_data, colWidths=[2.5 * inch, 3.5 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
    ]))

    story.append(table)
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph("<i>Note: Sensitive information redacted for privacy.</i>", styles["Normal"]))

    doc.build(story)
    return output_path