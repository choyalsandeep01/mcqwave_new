import hashlib
import json
import requests
from django.conf import settings
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

def generate_hash(data, salt):
    """Generate PayU hash with exact PayU specifications"""
    
    # Extract and clean all parameters
    key = str(data['key']).strip()
    txnid = str(data['txnid']).strip()
    amount = str(data['amount']).strip()
    productinfo = str(data['productinfo']).strip()
    firstname = str(data['firstname']).strip()
    email = str(data['email']).strip()
    udf1 = str(data.get('udf1', '')).strip()
    udf2 = str(data.get('udf2', '')).strip()
    udf3 = str(data.get('udf3', '')).strip()
    udf4 = str(data.get('udf4', '')).strip()
    udf5 = str(data.get('udf5', '')).strip()
    
    # PayU hash sequence: key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||salt
    hash_sequence = f"{key}|{txnid}|{amount}|{productinfo}|{firstname}|{email}|{udf1}|{udf2}|{udf3}|{udf4}|{udf5}||||||{salt}"
    
    # Generate SHA512 hash
    hash_value = hashlib.sha512(hash_sequence.encode('utf-8')).hexdigest().lower()
    
    logger.info(f"=== HASH CALCULATION DEBUG ===")
    logger.info(f"Hash sequence: {hash_sequence}")
    logger.info(f"Generated hash: {hash_value}")
    
    return hash_value

def verify_payment_hash(response_data, salt):
    """Verify PayU response hash"""
    status = str(response_data.get('status', '')).strip()
    udf5 = str(response_data.get('udf5', '')).strip()
    udf4 = str(response_data.get('udf4', '')).strip()
    udf3 = str(response_data.get('udf3', '')).strip()
    udf2 = str(response_data.get('udf2', '')).strip()
    udf1 = str(response_data.get('udf1', '')).strip()
    email = str(response_data.get('email', '')).strip()
    firstname = str(response_data.get('firstname', '')).strip()
    productinfo = str(response_data.get('productinfo', '')).strip()
    amount = str(response_data.get('amount', '')).strip()
    txnid = str(response_data.get('txnid', '')).strip()
    key = str(response_data.get('key', '')).strip()
    
    hash_sequence = f"{salt}|{status}|||||{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|{email}|{firstname}|{productinfo}|{amount}|{txnid}|{key}"
    calculated_hash = hashlib.sha512(hash_sequence.encode('utf-8')).hexdigest().lower()
    
    return calculated_hash

def prepare_payu_data(transaction, user):
    """Prepare data for PayU Bolt integration"""
    try:
        # Get base URL
        base_url = settings.BASE_DOMAIN.rstrip('/')
        success_url = f"{base_url}/payment/success/"
        failure_url = f"{base_url}/payment/failure/"
        
        # Clean phone number
        phone = getattr(user, 'phone', None) or '9999999999'
        phone = str(phone).strip()
        phone = ''.join(filter(str.isdigit, phone))[-10:]
        if len(phone) < 10:
            phone = '9999999999'
        
        # Clean product info - remove problematic characters
        category_display = str(transaction.plan.get_category_display()).replace('&', 'and').replace('|', '-')
        plan_name = str(transaction.plan.name).replace('|', '-')
        product_info = f"{category_display} - {plan_name}"
        
        # Prepare data
        payu_data = {
            'key': str(settings.PAYU_MERCHANT_KEY).strip(),
            'txnid': str(transaction.transaction_id).strip(),
            'amount': f"{float(transaction.amount):.2f}",
            'productinfo': product_info,
            'firstname': str(user.first_name or user.username)[:20].strip(),
            'email': str(user.email).strip(),
            'phone': str(phone),
            'surl': success_url,
            'furl': failure_url,
            'udf1': str(transaction.uid)[:255] if hasattr(transaction, 'uid') else '',
            'udf2': str(transaction.plan.category)[:255],
            'udf3': str(user.username)[:20].strip(),
            'udf4': '',
            'udf5': ''
        }
        
        # Generate hash
        payu_data['hash'] = generate_hash(payu_data, settings.PAYU_SALT)
        
        logger.info(f"PayU data prepared successfully for transaction: {transaction.transaction_id}")
        logger.info(f"Success URL: {success_url}")
        logger.info(f"Product info: {product_info}")
        
        return payu_data
        
    except Exception as e:
        logger.error(f"Error in prepare_payu_data: {str(e)}")
        raise Exception(f"PayU data preparation failed: {str(e)}")

class PayUBoltConfig:
    """PayU Bolt configuration"""
    
    @staticmethod
    def get_bolt_config(payu_data):
        """Return configuration for Bolt SDK with all required parameters"""
        try:
            config = {
                'key': payu_data['key'],
                'txnid': payu_data['txnid'],
                'amount': payu_data['amount'],
                'hash': payu_data['hash'],
                'firstname': payu_data['firstname'],
                'email': payu_data['email'],
                'phone': payu_data['phone'],
                'productinfo': payu_data['productinfo'],
                'surl': payu_data['surl'],  # Required for Bolt
                'furl': payu_data['furl'],  # Required for Bolt
                'udf1': payu_data.get('udf1', ''),
                'udf2': payu_data.get('udf2', ''),
                'udf3': payu_data.get('udf3', ''),
                'udf4': payu_data.get('udf4', ''),
                'udf5': payu_data.get('udf5', '')
            }
            
            logger.info(f"Bolt config created with {len(config)} parameters")
            logger.info(f"Config includes surl: {'surl' in config}")
            logger.info(f"Config includes furl: {'furl' in config}")
            
            return config
            
        except Exception as e:
            logger.error(f"Error creating Bolt config: {str(e)}")
            raise Exception(f"Bolt config creation failed: {str(e)}")
