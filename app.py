from flask import Flask, request, jsonify
import requests
from simple_salesforce import Salesforce
import json

app = Flask(__name__)

# Salesforce credentials (store securely in production)
SF_USERNAME = 'balaji.j@terralogic.com'
SF_PASSWORD = 'Balu@3303'
SF_SECURITY_TOKEN = 'lvq4mJ6Oi6a7aPv6arl8P70y3'
SF_DOMAIN = 'login'

OCR_API_URL = 'https://clickscanstg.terralogic.com/ocr/invoice/'

@app.route('/handle-invoice', methods=['POST'])
def handle_invoice():
    try:
        data = request.get_json()
        document_id = data.get('documentId')
        case_id = data.get('caseId')

        if not document_id or not case_id:
            return jsonify({'error': 'Missing documentId or caseId'}), 400

        # Step 1: Login to Salesforce
        sf = Salesforce(username=SF_USERNAME,
                        password=SF_PASSWORD,
                        security_token=SF_SECURITY_TOKEN,
                        domain=SF_DOMAIN)

        # Step 2: Get latest ContentVersion
        query = f"""
            SELECT Id, Title, FileExtension
            FROM ContentVersion
            WHERE ContentDocumentId = '{document_id}'
            ORDER BY CreatedDate DESC
            LIMIT 1
        """
        result = sf.query(query)
        if not result['records']:
            return jsonify({'error': 'No file found'}), 404

        version = result['records'][0]
        version_id = version['Id']
        filename = version['Title'] + '.' + version['FileExtension']

        # Step 3: Download binary file
        file_url = f"{sf.base_url}sobjects/ContentVersion/{version_id}/VersionData"
        file_res = requests.get(file_url, headers={"Authorization": "Bearer " + sf.session_id})

        if file_res.status_code != 200:
            return jsonify({'error': 'Failed to download file'}), 500

        # Step 4: Send to OCR
        files = {
            'file': (filename, file_res.content, 'application/octet-stream')
        }
        ocr_res = requests.post(OCR_API_URL, files=files)

        if ocr_res.status_code != 200:
            return jsonify({
                'error': 'OCR API failed',
                'statusCode': ocr_res.status_code,
                'response': ocr_res.text
            }), 502

        ocr_data = ocr_res.json()
        parsed_data = ocr_data.get('ocrResult', {}).get('parsedData', {})

        # Step 5: Store parsedData into Invoice__c (in Invoice__c text field)
        parsed_text = json.dumps(parsed_data, indent=2)

        invoice_data = {
            'Case__c': case_id,
            'Invoice__c': parsed_text  # 📝 Store parsedData as string
        }

        inserted = sf.Invoice__c.create(invoice_data)

        return jsonify({
            'status': 'success',
            'invoiceId': inserted.get('id'),
            'parsedData': parsed_data
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)
