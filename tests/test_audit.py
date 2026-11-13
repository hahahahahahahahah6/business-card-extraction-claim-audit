import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from business_card_extraction_claim_audit.audit import audit, claims, evidence
from business_card_extraction_claim_audit.__main__ import main
from business_card_extraction_claim_audit import phrases

ORACLE = (('business card extraction', 'extract business cards', 'extracts business cards', 'extracting business cards', 'extract business card', 'extracts business card', 'extracting business card', 'business card parsing', 'business card parser', 'parse business cards', 'parses business cards', 'parse business card', 'parses business card', 'business card scanning', 'business card scanner', 'scan business cards', 'scans business cards', 'scan business card', 'scans business card', 'business contact extraction', 'extract business contacts', 'extracts business contacts', 'extracting business contacts', 'extract business contact', 'extracts business contact', 'extracting business contact', 'business contact parsing', 'business contact parser', 'parse business contacts', 'parses business contacts', 'parse business contact', 'parses business contact', 'contact card extraction', 'extract contact cards', 'extracts contact cards', 'extracting contact cards', 'extract contact card', 'extracts contact card', 'extracting contact card', 'contact card parsing', 'contact card parser', 'parse contact cards', 'parses contact cards', 'parse contact card', 'parses contact card', 'business card data extraction', 'extract business card data', 'business card field extraction', 'business card document extraction', 'extract business card documents'), ('no business card extraction', 'does not extract business cards', 'does not extract business card', 'does not support business card extraction', 'without business card extraction', 'no business contact extraction', 'does not extract business contacts', 'does not extract business contact', 'does not support business contact extraction', 'without business contact extraction', 'no contact card extraction', 'does not extract contact cards', 'does not extract contact card', 'does not support contact card extraction', 'without contact card extraction', 'business card extraction not supported', 'business contact extraction not supported', 'contact card extraction not supported', 'no business card parser', 'does not parse business cards', 'does not parse business card', 'no business card scanner', 'does not scan business cards', 'does not scan business card'), ('extract_business_card', 'extract_business_cards', 'parse_business_card', 'parse_business_cards', 'extract_business_contact', 'extract_business_contacts', 'parse_business_contact', 'parse_business_contacts', 'extract_contact_card', 'extract_contact_cards', 'parse_contact_card', 'parse_contact_cards', 'extract_business_card_data', 'parse_business_card_data', 'business_card_extraction', 'business_card_extractor', 'business_card_parser', 'contact_card_extraction', 'extract_business_card_info', 'parse_business_card_info', 'business_card_scan', 'business_card_scanner', 'scan_business_card', 'scan_business_cards'))

class AuditTests(unittest.TestCase):
    def fixture(self, text='We extract business cards.', files=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'README.md').write_text(text)
        for name, source in (files or {}).items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        return root

    def cli(self, root, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main(['audit', str(root), '--json', *args])
        return status, json.loads(out.getvalue())

    def test_phrase_oracle(self):
        tree = ast.parse(Path(phrases.__file__).read_text())
        actual = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)}
        self.assertEqual(tuple(actual[n] for n in ('BUSINESSCARDEXTRACTION', 'NOBUSINESSCARDEXTRACTION', 'GENERIC_NAMES')), ORACLE)
        self.assertEqual(tuple(map(len, ORACLE)), (50, 24, 24))

    def test_bad(self):
        status, data = self.cli(self.fixture())
        self.assertEqual(status, 2)
        self.assertEqual(data['verdict'], 'FAIL')
        self.assertEqual(data['findings'][0]['id'], 'documented-business-card-extraction-claim-false')
        self.assertEqual(data['findings'][0]['severity'], 'HIGH')
        self.assertTrue(data['findings'][0]['message'])

    def test_good(self):
        self.assertEqual(self.cli(self.fixture(files={'app.py': 'x.extract_business_card()'}))[0], 0)

    def test_test_only(self):
        for name in ('tests/app.py', 'test_app.py', 'app_test.py'):
            root = self.fixture(files={name: 'x.extract_business_card()'})
            self.assertEqual(self.cli(root)[0], 0)
            self.assertEqual(self.cli(root)[1]['findings'][0]['severity'], 'MEDIUM')
            self.assertEqual(self.cli(root, '--fail-on', 'medium')[0], 2)

    def test_denial(self):
        root = self.fixture('Does not extract business cards.', {'app.py': 'x.extract_business_card()'})
        status, data = self.cli(root)
        self.assertEqual(status, 2)
        self.assertEqual(len(data['findings']), 1)
        self.assertEqual(data['findings'][0]['id'], 'documented-no-business-card-extraction-claim-false')
        self.assertEqual(data['findings'][0]['severity'], 'HIGH')

    def test_no_claim(self):
        self.assertEqual(audit(self.fixture('Hello', {'app.py': 'x.extract_business_card()'}))['verdict'], 'PASS')

    def test_no_source_denial(self):
        self.assertEqual(audit(self.fixture('No business card extraction'))['verdict'], 'PASS')

    def test_fences(self):
        for fence in ('```', '~~~', '   ````'):
            self.assertEqual(claims(fence+'\nextract business cards\n'+fence), (False, False))
        self.assertEqual(claims('`extract business cards`'), (True, False))
        self.assertEqual(claims("doesn't extract business cards"), (False, True))
        self.assertEqual(claims('extract-business-cards'), (True, False))
        self.assertEqual(claims('extract business cardsx'), (False, False))

    def test_docs_and_exclusions(self):
        root = self.fixture('Hello', {'nested/docs/a.md': 'extract business cards', 'other.md': 'extract business cards', 'fixtures/a.py': 'x.extract_business_card()', 'docs/a.py': 'x.extract_business_card()', 'examples/a.py': 'x.extract_business_card()'})
        self.assertEqual(audit(root)['findings'][0]['docs'], ['nested/docs/a.md'])
        self.assertEqual(audit(root, ['nested'])['verdict'], 'PASS')

    def test_symlinks(self):
        root = self.fixture()
        external = self.fixture(files={'a.py': 'x.extract_business_card()'})
        (root/'a.py').symlink_to(external/'a.py')
        (root/'linked').symlink_to(external, target_is_directory=True)
        self.assertEqual(audit(root)['production_evidence'], [])

    def test_split_module(self):
        root = self.fixture(files={'a.py': 'from mindee import Client\nc=Client()', 'b.py': 'c.parse(product.BusinessCardV1, doc)'})
        self.assertEqual(self.cli(root)[0], 2)

    def test_version_and_module(self):
        result = subprocess.run([sys.executable, '-m', 'business_card_extraction_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '0.1.0'))
        result = subprocess.run([sys.executable, '-m', 'business_card_extraction_claim_audit', 'audit', str(self.fixture('Hello'))], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'PASS'))

    def test_usage_errors(self):
        for args in ([], ['audit', '--fail-on', 'HIGH'], ['audit', '--ignore', 'a', 'b', 'c']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['audit', '/nonexistent-r197-directory']), 1)

    def test_yes_0_generic_extract_business_card(self):
        self.assertTrue(evidence('x.extract_business_card()'))

    def test_yes_1_import_extract_business_card(self):
        self.assertTrue(evidence('from vendor import extract_business_card as op\nop()'))

    def test_yes_2_generic_extract_business_cards(self):
        self.assertTrue(evidence('x.extract_business_cards()'))

    def test_yes_3_import_extract_business_cards(self):
        self.assertTrue(evidence('from vendor import extract_business_cards as op\nop()'))

    def test_yes_4_generic_parse_business_card(self):
        self.assertTrue(evidence('x.parse_business_card()'))

    def test_yes_5_import_parse_business_card(self):
        self.assertTrue(evidence('from vendor import parse_business_card as op\nop()'))

    def test_yes_6_generic_parse_business_cards(self):
        self.assertTrue(evidence('x.parse_business_cards()'))

    def test_yes_7_import_parse_business_cards(self):
        self.assertTrue(evidence('from vendor import parse_business_cards as op\nop()'))

    def test_yes_8_generic_extract_business_contact(self):
        self.assertTrue(evidence('x.extract_business_contact()'))

    def test_yes_9_import_extract_business_contact(self):
        self.assertTrue(evidence('from vendor import extract_business_contact as op\nop()'))

    def test_yes_10_generic_extract_business_contacts(self):
        self.assertTrue(evidence('x.extract_business_contacts()'))

    def test_yes_11_import_extract_business_contacts(self):
        self.assertTrue(evidence('from vendor import extract_business_contacts as op\nop()'))

    def test_yes_12_generic_parse_business_contact(self):
        self.assertTrue(evidence('x.parse_business_contact()'))

    def test_yes_13_import_parse_business_contact(self):
        self.assertTrue(evidence('from vendor import parse_business_contact as op\nop()'))

    def test_yes_14_generic_parse_business_contacts(self):
        self.assertTrue(evidence('x.parse_business_contacts()'))

    def test_yes_15_import_parse_business_contacts(self):
        self.assertTrue(evidence('from vendor import parse_business_contacts as op\nop()'))

    def test_yes_16_generic_extract_contact_card(self):
        self.assertTrue(evidence('x.extract_contact_card()'))

    def test_yes_17_import_extract_contact_card(self):
        self.assertTrue(evidence('from vendor import extract_contact_card as op\nop()'))

    def test_yes_18_generic_extract_contact_cards(self):
        self.assertTrue(evidence('x.extract_contact_cards()'))

    def test_yes_19_import_extract_contact_cards(self):
        self.assertTrue(evidence('from vendor import extract_contact_cards as op\nop()'))

    def test_yes_20_generic_parse_contact_card(self):
        self.assertTrue(evidence('x.parse_contact_card()'))

    def test_yes_21_import_parse_contact_card(self):
        self.assertTrue(evidence('from vendor import parse_contact_card as op\nop()'))

    def test_yes_22_generic_parse_contact_cards(self):
        self.assertTrue(evidence('x.parse_contact_cards()'))

    def test_yes_23_import_parse_contact_cards(self):
        self.assertTrue(evidence('from vendor import parse_contact_cards as op\nop()'))

    def test_yes_24_generic_extract_business_card_data(self):
        self.assertTrue(evidence('x.extract_business_card_data()'))

    def test_yes_25_import_extract_business_card_data(self):
        self.assertTrue(evidence('from vendor import extract_business_card_data as op\nop()'))

    def test_yes_26_generic_parse_business_card_data(self):
        self.assertTrue(evidence('x.parse_business_card_data()'))

    def test_yes_27_import_parse_business_card_data(self):
        self.assertTrue(evidence('from vendor import parse_business_card_data as op\nop()'))

    def test_yes_28_generic_business_card_extraction(self):
        self.assertTrue(evidence('x.business_card_extraction()'))

    def test_yes_29_import_business_card_extraction(self):
        self.assertTrue(evidence('from vendor import business_card_extraction as op\nop()'))

    def test_yes_30_generic_business_card_extractor(self):
        self.assertTrue(evidence('x.business_card_extractor()'))

    def test_yes_31_import_business_card_extractor(self):
        self.assertTrue(evidence('from vendor import business_card_extractor as op\nop()'))

    def test_yes_32_generic_business_card_parser(self):
        self.assertTrue(evidence('x.business_card_parser()'))

    def test_yes_33_import_business_card_parser(self):
        self.assertTrue(evidence('from vendor import business_card_parser as op\nop()'))

    def test_yes_34_generic_contact_card_extraction(self):
        self.assertTrue(evidence('x.contact_card_extraction()'))

    def test_yes_35_import_contact_card_extraction(self):
        self.assertTrue(evidence('from vendor import contact_card_extraction as op\nop()'))

    def test_yes_36_generic_extract_business_card_info(self):
        self.assertTrue(evidence('x.extract_business_card_info()'))

    def test_yes_37_import_extract_business_card_info(self):
        self.assertTrue(evidence('from vendor import extract_business_card_info as op\nop()'))

    def test_yes_38_generic_parse_business_card_info(self):
        self.assertTrue(evidence('x.parse_business_card_info()'))

    def test_yes_39_import_parse_business_card_info(self):
        self.assertTrue(evidence('from vendor import parse_business_card_info as op\nop()'))

    def test_yes_40_generic_business_card_scan(self):
        self.assertTrue(evidence('x.business_card_scan()'))

    def test_yes_41_import_business_card_scan(self):
        self.assertTrue(evidence('from vendor import business_card_scan as op\nop()'))

    def test_yes_42_generic_business_card_scanner(self):
        self.assertTrue(evidence('x.business_card_scanner()'))

    def test_yes_43_import_business_card_scanner(self):
        self.assertTrue(evidence('from vendor import business_card_scanner as op\nop()'))

    def test_yes_44_generic_scan_business_card(self):
        self.assertTrue(evidence('x.scan_business_card()'))

    def test_yes_45_import_scan_business_card(self):
        self.assertTrue(evidence('from vendor import scan_business_card as op\nop()'))

    def test_yes_46_generic_scan_business_cards(self):
        self.assertTrue(evidence('x.scan_business_cards()'))

    def test_yes_47_import_scan_business_cards(self):
        self.assertTrue(evidence('from vendor import scan_business_cards as op\nop()'))

    def test_yes_48_azure_pos(self):
        self.assertTrue(evidence('from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document("prebuilt-businessCard", doc)'))

    def test_yes_49_azure_keyword(self):
        self.assertTrue(evidence('from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document(model_id="prebuilt-businessCard")'))

    def test_yes_50_azure_intelligence(self):
        self.assertTrue(evidence('import azure.ai.documentintelligence as ai\nc=ai.DocumentIntelligenceClient()\nc.begin_analyze_document_from_url("prebuilt-businessCard", url)'))

    def test_yes_51_azure_full(self):
        self.assertTrue(evidence('import azure.ai.formrecognizer\nc=azure.ai.formrecognizer.DocumentAnalysisClient()\nc.begin_analyze_document("prebuilt-businessCard")'))

    def test_yes_52_mindee_52(self):
        self.assertTrue(evidence('from mindee import Client as C\nc=C()\nc.parse(product=BusinessCardV1)'))

    def test_yes_53_mindee_53(self):
        self.assertTrue(evidence('from mindee import Client as C\nc=C()\nc.parse(product=product.BusinessCardV1)'))

    def test_yes_54_mindee_54(self):
        self.assertTrue(evidence('from mindee import Client as C\nc=C()\nc.parse(product=mindee.product.BusinessCardV1)'))

    def test_yes_55_process_bussines_card_document(self):
        self.assertTrue(evidence('import veryfi\nc=veryfi.Client()\nc.process_bussines_card_document(doc)'))

    def test_yes_56_process_bussines_card_document_url(self):
        self.assertTrue(evidence('import veryfi\nc=veryfi.Client()\nc.process_bussines_card_document_url(doc)'))

    def test_no_0_azure_prebuilt_invoice(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-invoice')"))

    def test_no_1_azure_prebuilt_receipt(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-receipt')"))

    def test_no_2_azure_prebuilt_layout(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-layout')"))

    def test_no_3_azure_prebuilt_read(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-read')"))

    def test_no_4_azure_prebuilt_idDocument(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-idDocument')"))

    def test_no_5_azure_prebuilt_check_us(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-check.us')"))

    def test_no_6_azure_prebuilt_tax_us(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-tax.us')"))

    def test_no_7_azure_prebuilt_bankStatement_us(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-bankStatement.us')"))

    def test_no_8_azure_prebuilt_payStub_us(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-payStub.us')"))

    def test_no_9_azure_prebuilt_healthInsuranceCard_us(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-healthInsuranceCard.us')"))

    def test_no_10_azure_prebuilt_businessCard_us(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-businessCard.us')"))

    def test_no_11_azure_prebuilt_businesscard(self):
        self.assertFalse(evidence("from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\nc.begin_analyze_document('prebuilt-businesscard')"))

    def test_no_12_mindee_InvoiceV4(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.InvoiceV4, doc)'))

    def test_no_13_mindee_ReceiptV5(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.ReceiptV5, doc)'))

    def test_no_14_mindee_PassportV1(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.PassportV1, doc)'))

    def test_no_15_mindee_FinancialDocumentV1(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.FinancialDocumentV1, doc)'))

    def test_no_16_mindee_BankCheckV1(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.BankCheckV1, doc)'))

    def test_no_17_mindee_BankAccountDetailsV2(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.BankAccountDetailsV2, doc)'))

    def test_no_18_mindee_PayslipV2(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.PayslipV2, doc)'))

    def test_no_19_mindee_PayslipV3(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.PayslipV3, doc)'))

    def test_no_20_mindee_HealthcareCardV1(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.HealthcareCardV1, doc)'))

    def test_no_21_mindee_CustomV1(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.CustomV1, doc)'))

    def test_no_22_mindee_BusinessCardV2(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()\nc.parse(product.BusinessCardV2, doc)'))

    def test_no_23_veryfi_process_any_document(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_any_document(doc)'))

    def test_no_24_veryfi_process_any_document_url(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_any_document_url(doc)'))

    def test_no_25_veryfi_process_document(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_document(doc)'))

    def test_no_26_veryfi_process_document_url(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_document_url(doc)'))

    def test_no_27_veryfi_process_w2_document(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_w2_document(doc)'))

    def test_no_28_veryfi_process_w9_document(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_w9_document(doc)'))

    def test_no_29_veryfi_process_w8_document(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_w8_document(doc)'))

    def test_no_30_veryfi_process_check(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_check(doc)'))

    def test_no_31_veryfi_process_check_url(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_check_url(doc)'))

    def test_no_32_veryfi_process_check_with_remittance(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_check_with_remittance(doc)'))

    def test_no_33_veryfi_process_check_with_remittance_url(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_check_with_remittance_url(doc)'))

    def test_no_34_veryfi_process_bank_statement_document(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_bank_statement_document(doc)'))

    def test_no_35_veryfi_process_bank_statement_document_url(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_bank_statement_document_url(doc)'))

    def test_no_36_veryfi_process_business_card_document(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_business_card_document(doc)'))

    def test_no_37_veryfi_process_business_card_document_url(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_business_card_document_url(doc)'))

    def test_no_38_veryfi_process_health_insurance_card(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.process_health_insurance_card(doc)'))

    def test_no_39_veryfi_classify_document(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.classify_document(doc)'))

    def test_no_40_veryfi_get_business_cards(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.get_business_cards(doc)'))

    def test_no_41_veryfi_get_business_card(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.get_business_card(doc)'))

    def test_no_42_veryfi_delete_business_card(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()\nc.delete_business_card(doc)'))

    def test_no_43_misc_0(self):
        self.assertFalse(evidence('import mindee'))

    def test_no_44_misc_1(self):
        self.assertFalse(evidence('import veryfi'))

    def test_no_45_misc_2(self):
        self.assertFalse(evidence('import azure.ai.formrecognizer'))

    def test_no_46_misc_3(self):
        self.assertFalse(evidence('import mindee\nc=mindee.Client()'))

    def test_no_47_misc_4(self):
        self.assertFalse(evidence('from azure.ai.formrecognizer import DocumentAnalysisClient as C\nc=C()\n'))

    def test_no_48_misc_5(self):
        self.assertFalse(evidence('import veryfi\nc=veryfi.Client()'))

    def test_no_49_misc_6(self):
        self.assertFalse(evidence('c.parse(product.BusinessCardV1, doc)'))

    def test_no_50_misc_7(self):
        self.assertFalse(evidence('x.process_bussines_card_document(doc)'))

    def test_no_51_misc_8(self):
        self.assertFalse(evidence('x.begin_analyze_document("prebuilt-businessCard")'))

    def test_no_52_misc_9(self):
        self.assertFalse(evidence('extract_business_card()'))

    def test_no_53_misc_10(self):
        self.assertFalse(evidence('x.extract_business_card'))

    def test_no_54_misc_11(self):
        self.assertFalse(evidence('"x.extract_business_card()"'))

    def test_no_55_misc_12(self):
        self.assertFalse(evidence('# x.extract_business_card()'))

    def test_no_56_misc_13(self):
        self.assertFalse(evidence('invalid syntax !'))

    def test_no_57_misc_14(self):
        self.assertFalse(evidence('re.findall("name", ocr_text)'))

    def test_no_58_misc_15(self):
        self.assertFalse(evidence('text.split(":")'))

    def test_no_59_misc_16(self):
        self.assertFalse(evidence('subprocess.run(["mindee", "parse", "card.jpg"])'))

    def test_no_60_misc_17(self):
        self.assertFalse(evidence('subprocess.run(["veryfi", "card.jpg"])'))

    def test_no_61_adjacent_analyze_document(self):
        self.assertFalse(evidence('x.analyze_document(doc)'))

    def test_no_62_adjacent_analyze_expense(self):
        self.assertFalse(evidence('x.analyze_expense(doc)'))

    def test_no_63_adjacent_start_document_analysis(self):
        self.assertFalse(evidence('x.start_document_analysis(doc)'))

    def test_no_64_adjacent_get_expense_analysis(self):
        self.assertFalse(evidence('x.get_expense_analysis(doc)'))

    def test_no_65_adjacent_extract_text(self):
        self.assertFalse(evidence('x.extract_text(doc)'))

    def test_no_66_adjacent_image_to_string(self):
        self.assertFalse(evidence('x.image_to_string(doc)'))

    def test_no_67_adjacent_read_csv(self):
        self.assertFalse(evidence('x.read_csv(doc)'))

    def test_no_68_adjacent_read_excel(self):
        self.assertFalse(evidence('x.read_excel(doc)'))

    def test_no_69_adjacent_read_pdf(self):
        self.assertFalse(evidence('x.read_pdf(doc)'))

    def test_no_70_adjacent_convert_into(self):
        self.assertFalse(evidence('x.convert_into(doc)'))

    def test_no_71_adjacent_extract_table(self):
        self.assertFalse(evidence('x.extract_table(doc)'))

    def test_no_72_adjacent_extract_tables(self):
        self.assertFalse(evidence('x.extract_tables(doc)'))

    def test_no_73_adjacent_find_table(self):
        self.assertFalse(evidence('x.find_table(doc)'))

    def test_no_74_adjacent_find_tables(self):
        self.assertFalse(evidence('x.find_tables(doc)'))

    def test_no_75_shadow_0(self):
        self.assertFalse(evidence('from vendor import extract_business_card\ndef extract_business_card(): pass\nextract_business_card()\nx.extract_business_card()'))

    def test_no_76_shadow_1(self):
        self.assertFalse(evidence('from vendor import extract_business_card\nclass extract_business_card: pass\nextract_business_card()\nx.extract_business_card()'))

    def test_no_77_shadow_2(self):
        self.assertFalse(evidence('from vendor import extract_business_card\nclass Other:\n def extract_business_card(self): pass\nextract_business_card()\nx.extract_business_card()'))

    def test_no_78_shadow_3(self):
        self.assertFalse(evidence('from vendor import extract_business_card\nextract_business_card = other\nextract_business_card()\nx.extract_business_card()'))

    def test_no_79_shadow_4(self):
        self.assertFalse(evidence('from vendor import extract_business_card\nextract_business_card: object = other\nextract_business_card()\nx.extract_business_card()'))

    def test_no_80_shadow_5(self):
        self.assertFalse(evidence('from vendor import extract_business_card\nwith context() as extract_business_card: pass\nextract_business_card()\nx.extract_business_card()'))

    def test_no_81_shadow_6(self):
        self.assertFalse(evidence('from vendor import extract_business_card\nasync def f():\n async with context() as extract_business_card: pass\nextract_business_card()\nx.extract_business_card()'))

    def test_no_82_client_shadow_0(self):
        self.assertFalse(evidence('from veryfi import Client as C\nC = object\nc=C()\nc.process_bussines_card_document(doc)'))

    def test_no_83_client_shadow_1(self):
        self.assertFalse(evidence('from veryfi import Client as C\nC: object = other\nc=C()\nc.process_bussines_card_document(doc)'))

    def test_no_84_client_shadow_2(self):
        self.assertFalse(evidence('from veryfi import Client as C\nwith context() as C: pass\nc=C()\nc.process_bussines_card_document(doc)'))

    def test_no_85_client_shadow_3(self):
        self.assertFalse(evidence('from veryfi import Client as C\ndef C(): pass\nc=C()\nc.process_bussines_card_document(doc)'))


    def test_qualified_vendor_constructor_boundaries(self):
        for vendor, operation in [('mindee', 'parse(product.BusinessCardV1, doc)'), ('veryfi', 'process_bussines_card_document(doc)')]:
            self.assertFalse(evidence('import '+vendor+' as v\nc=v.Client()\nc.'+operation))
            self.assertTrue(evidence('from '+vendor+' import Client as C\nc=C()\nc.'+operation))

    def test_all_phrases(self):
        for phrase in ORACLE[0]:
            self.assertEqual(claims(phrase), (True, False), phrase)
        for phrase in ORACLE[1]:
            self.assertEqual(claims(phrase), (False, True), phrase)

    def test_route_definition_shadows(self):
        for route, setup, call in [
            ('parse', 'import mindee\nc=mindee.Client()', 'c.parse(product.BusinessCardV1, doc)'),
            ('begin_analyze_document', 'from azure.ai.formrecognizer import DocumentAnalysisClient\nc=DocumentAnalysisClient()', 'c.begin_analyze_document("prebuilt-businessCard")'),
            ('process_bussines_card_document', 'import veryfi\nc=veryfi.Client()', 'c.process_bussines_card_document(doc)')]:
            self.assertFalse(evidence(setup+'\ndef '+route+'(): pass\n'+call))

    def test_ignore_component_boundary(self):
        root = self.fixture(files={'vendorish/a.py': 'x.extract_business_card()', 'vendor/a.py': 'x.extract_business_card()'})
        self.assertEqual(audit(root, ['vendor'])['production_evidence'], ['vendorish/a.py'])

    def test_verbose(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = main(['audit', str(self.fixture(files={'app.py': 'x.extract_business_card()'})), '--verbose'])
        self.assertEqual(status, 0)
        self.assertIn('app.py', out.getvalue())

if __name__ == "__main__":
    unittest.main()
