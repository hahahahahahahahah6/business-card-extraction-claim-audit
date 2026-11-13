# Documentation claim auditor

An offline, read-only audit tool compares documented promises with recognizable calls in Python source. It uses the standard library, parses source without executing it, makes no network calls, and writes no files.

## Installation and usage

```sh
python3 -m venv .venv
.venv/bin/pip install .
business-card-extraction-claim-audit --version
business-card-extraction-claim-audit audit .
python3 -m business_card_extraction_claim_audit audit . --json
business-card-extraction-claim-audit audit . --verbose --fail-on medium --ignore vendor --ignore generated
python3 -m unittest discover
python3 -m build
```

The repository defaults to the current directory. Each ignore option accepts one relative path prefix with component boundaries. The threshold accepts lowercase high or medium and defaults to high. Version output is 0.1.0. JSON contains verdict, findings, production_evidence, and test_evidence; findings contain id, severity, message, and docs. Verbose text includes evidence paths.

Exit status is 0 without findings meeting the threshold, 2 with findings meeting it, and 1 for usage or I/O errors. A MEDIUM finding produces a FAIL verdict but status 0 at the default threshold. A positive promise without production evidence is HIGH, or MEDIUM if evidence exists only in tests. A denial contradicted by production evidence is HIGH. There is at most one finding per direction. With no source files, a positive promise fails and a denial passes.

```text
documented-business-card-extraction-claim-false
documented-no-business-card-extraction-claim-false
```

## Matching rules

Root README.md and Markdown files under any docs path component are checked. Backtick and tilde fences with up to three leading spaces are excluded; inline code counts. Paragraphs split on blank lines. Matching lowercases text, expands negative contractions, replaces hyphens with spaces, and collapses whitespace. Exact phrases use word boundaries, longest first with alphabetical ties. Denial spans are removed before positive matching. The fixed vocabulary has 50 positive phrases, 24 denials, and 24 generic operation names.

Source inspection excludes symlinks and files under fixtures, docs, or examples. Files under tests or named test_*.py or *_test.py contribute only test evidence. Invalid syntax gives no evidence. Paired calls must occur in one module. Import aliases are resolved; local functions, methods, classes, assignments, annotated assignments, and context-manager bindings shadow imported names. Bare imports and bare references do not count.

The checked capability concerns structured contact first and last names, company, department, job title, email, website, address, and mobile, work, fax, and other phone fields from printed cards. The following routes count. Generic attribute calls accept any base; bare names require a matching from-import. A locally defined route name suppresses that route.

```text
Azure import gate: azure.ai.formrecognizer or azure.ai.documentintelligence
DocumentAnalysisClient or DocumentIntelligenceClient construction plus
begin_analyze_document or begin_analyze_document_from_url
first positional argument or model_id keyword exactly "prebuilt-businessCard"

mindee import + Client construction + parse(BusinessCardV1, ...)
Also accepts product.BusinessCardV1 and mindee.product.BusinessCardV1,
including keyword arguments. This fixed product uses endpoint_name
"business_card", version 1, and returns structured contact fields.

veryfi import + Client construction + process_bussines_card_document
or process_bussines_card_document_url. The SDK spells "bussines" (one s).

Generic names:
extract_business_card
extract_business_cards
parse_business_card
parse_business_cards
extract_business_contact
extract_business_contacts
parse_business_contact
parse_business_contacts
extract_contact_card
extract_contact_cards
parse_contact_card
parse_contact_cards
extract_business_card_data
parse_business_card_data
business_card_extraction
business_card_extractor
business_card_parser
contact_card_extraction
extract_business_card_info
parse_business_card_info
business_card_scan
business_card_scanner
scan_business_card
scan_business_cards
```

## Honest limitations

Static patterns do not establish semantic correctness. Dead code counts; alias chains may be missed. Exact vocabulary misses paraphrases, and denial handling depends on the fixed list. Cloud calls establish source evidence, not valid credentials or successful execution. The detailed boundaries below explain false positives, missed implementations, model lifecycle, and adjacent operations.

```text
- The bare phrases "business card extraction" / "extract business
  card" / "extract business cards" are deliberately
  BUSINESSCARDEXTRACTION phrases: in document-tool docs they
  almost always name business card extraction. But "business card"
  can also name a card image the tool merely displays, a card
  template the tool merely renders, or a digital business card the
  tool merely shares: a doc that means displaying, rendering, or
  sharing cards, not extracting fields from them, is a false
  positive; the tool flags the claim, only the code decides.
- "business contact extraction" / "extract business contact(s)"
  are deliberately phrases: "business contact" can also name a
  CRM contact record the tool merely stores or syncs, not a
  business card document the tool extracts fields from. The tool
  flags the claim; only the code decides.
- "contact card extraction" / "extract contact card(s)" are
  deliberately phrases: "contact card" can also name a vCard /
  .vcf contact file the tool merely imports, or an address-book
  contact card the tool merely displays, not a printed business
  card the tool extracts fields from. The tool flags the claim;
  only the code decides.
- "business card scanning" / "scan business card(s)" are
  deliberately phrases: "scanning" a card can mean merely
  photographing it or OCRing it into raw text, with no structured
  field extraction. The tool flags the claim; only the code
  decides.
- A generic `extract_business_card(` / `parse_business_card(`
  call can name a string parser for numbers the user typed in
  rather than a document extractor: the tool counts the call, the
  claim plus the code decide — and a subprocess call invoking an
  external CLI is NOT evidence by design, so a thin wrapper that
  only calls subprocess fails.
- Azure `begin_analyze_document` with model id
  "prebuilt-businessCard" counts as evidence even though the model
  is deprecated starting with Document Intelligence v4.0: the
  model is still GA in v3.1 (2023-07-31), v3.0, and v2.1, and the
  tool detects the client call in source, not whether the call
  succeeds against a current API version. 
- Azure `begin_analyze_document` with "prebuilt-businessCard.us"
  is NOT detected: no such model id exists — the business card
  model id has no ".us" suffix (unlike the US document models
  prebuilt-tax.us / prebuilt-payStub.us /
  prebuilt-healthInsuranceCard.us). 
- Azure `begin_analyze_document` with lowercase
  "prebuilt-businesscard" is NOT detected: model ids are matched
  case-sensitively and exactly — "prebuilt-businessCard" (capital
  B, capital C) counts, lowercase does not. (The Microsoft Learn
  language-support page lists shorthand labels in lowercase;
  those are table labels, not the model id.) 
- Mindee `parse` with BusinessCardV1 counts as evidence: the
  mindee BusinessCard product is the business card endpoint
  (endpoint_name "business_card"), a fixed product class that
  extracts business card fields (firstname, lastname, company,
  job title, email, phone numbers, address, website, social
  media), so it is a real business-card extraction operation.
  
- Veryfi `process_bussines_card_document` /
  `process_bussines_card_document_url` count as evidence: the
  veryfi SDK spells the method "bussines" (one s); the
  correctly-spelled process_business_card_document does not exist
  in the SDK, so a call to the correctly-spelled name counts as
  nothing. 
- Veryfi `process_any_document` / `process_any_document_url` are
  NOT detected: AnyDocs is generic configurable extraction, not a
  business-card operation. 
- Veryfi `process_document` is NOT detected: it processes generic
  receipts and invoices. Only a business-card method would count
  here. 
- Veryfi `process_w2_document` / `process_w9_document` /
  `process_w8_document` are NOT detected: tax forms are a separate
  document type covered by the tax-form family. Say so in the
  README.
- Veryfi `process_check` / `process_check_url` /
  `process_check_with_remittance` /
  `process_check_with_remittance_url` are NOT detected: checks are
  a separate document type covered by the bank-check family. Say
  so in the README.
- Veryfi `process_bank_statement_document` /
  `process_bank_statement_document_url` are NOT detected: bank
  statements are a separate document type covered by the
  bank-statement family. 
- Veryfi `get_business_cards` / `get_business_card` /
  `delete_business_card` are NOT detected: retrieval and
  management, not extraction. 
- Veryfi `classify_document` is NOT detected: classification, not
  extraction. 
- Azure `begin_analyze_document` with "prebuilt-invoice" /
  "prebuilt-receipt" / "prebuilt-layout" / "prebuilt-idDocument" /
  "prebuilt-check.us" / "prebuilt-tax.us" /
  "prebuilt-bankStatement.us" / "prebuilt-payStub.us" /
  "prebuilt-healthInsuranceCard.us" is NOT detected, for the same
  reason: invoices, receipts, layouts, ID documents, checks, tax
  forms, bank statements, pay stubs, and health insurance cards
  are separate document types covered by their own families. Say
  so in the README.
- Mindee `parse` with InvoiceV4 / ReceiptV5 / PassportV1 /
  FinancialDocumentV1 / BankCheckV1 / BankAccountDetailsV2 /
  PayslipV2 / PayslipV3 / HealthcareCardV1 / CustomV1 is NOT
  detected: those are other document types. 
- Textract `analyze_document` / `analyze_expense` /
  `start_document_analysis` / `get_expense_analysis` are NOT
  detected: generic document and expense analysis are not
  business card extraction, and Textract has no business card
  operation. 
- A hand-rolled extraction from OCR text (`re.search` /
  `re.findall` on extracted text plus manual field assembly, no
  listed call) is NOT detected: the tool requires a listed call.
  
- The mindee CLI, the veryfi CLI, and any other external business
  card tool invoked through subprocess are NOT detected:
  subprocess calls invoking an external CLI are NOT evidence by
  design. 
- Azure Document Intelligence, Mindee, and Veryfi are cloud APIs:
  the tool detects the client call in source, not whether
  credentials are configured or the call succeeds. Say so in the
  README.
- "extract contact name" / "extract company name" / "extract job
  title" claims are NOT in the phrase lists: contact names, company
  names, and job titles are contact data points, not business-card
  document extraction claims on their own. 
- Invoice extraction claims ("extract invoices", "invoice
  extraction"), receipt extraction claims ("extract receipts",
  "receipt extraction"), ID document extraction claims ("extract
  passports", "passport extraction"), bank check extraction claims
  ("extract bank checks", "check extraction"), bank statement
  extraction claims ("extract bank statements", "statement
  extraction"), tax form extraction claims ("extract tax forms",
  "extract w2 forms", "1099 extraction"), pay stub extraction
  claims ("extract pay stubs", "payslip extraction"), and health
  insurance card extraction claims ("extract health insurance
  cards", "health insurance card extraction") are NOT in the phrase
  lists: this family covers business cards only. 
- Business card design / printing claims ("design business cards",
  "print business cards", "business card templates") are NOT in the
  phrase lists: designing or printing cards is not extracting
  fields from them. 
- As with every family: static pattern matching, not semantic
  judgement; dead code counts; alias chains the tracer cannot follow
  are missed; exact phrases only, not semantics; denial handling
  depends on the denial phrase list; each route must sit in a single
  module.

```

Plain text and table operations also supply no evidence:

```text
pdfplumber / fitz / pypdf / PyPDF2 / pdfminer: extract_text
pytesseract: image_to_string
pandas: read_csv / read_excel
camelot: read_pdf
tabula: read_pdf / convert_into
pdfplumber: extract_table / extract_tables / find_table / find_tables
fitz: find_tables
veryfi: process_health_insurance_card (no such method exists)
```

## Differentiation

OCR checks text recognition and table audits check table structure. Invoice, receipt, ID, check, statement, tax, pay-stub, and health-plan-card audits check other document types. This audit checks the structured contact operation described above. Designing, printing, displaying, and sharing cards alone are outside the vocabulary.

## Development

The distribution bundles the test suite, including a fixed literal phrase oracle independent of the external specification. Both distributions can be built locally with the command above.
