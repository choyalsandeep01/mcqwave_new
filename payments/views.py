import json
import uuid
from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.middleware.csrf import get_token
from .models import PaymentPlan, PaymentTransaction, UserSubscription, UserSubscriptionManager
from .payu_utils import prepare_payu_data, PayUBoltConfig, verify_payment_hash
import logging

logger = logging.getLogger(__name__)

@login_required
def payment_plans(request):
    """Payment plans view with enhanced debugging"""
    
    # Get plans that are both active and visible
    visible_plans = PaymentPlan.objects.filter(
        is_active=True,
        active_config__is_visible=True
    ).select_related('active_config').order_by('category', 'active_config__display_order', 'duration_days')
    
    # Group plans by category
    categorized_plans = {
        'neet_pg_inicet': [],
        'fmge': [],
        'upsc_cms': []
    }
    
    for plan in visible_plans:
        if plan.category in categorized_plans:
            categorized_plans[plan.category].append(plan)
    
    # Get user subscriptions
    user_subscriptions = UserSubscription.objects.filter(
        user=request.user,
        is_active=True
    ).select_related('plan')
    
    # Process expired subscriptions
    active_subscriptions = []
    for subscription in user_subscriptions:
        if subscription.is_expired:
            subscription.is_active = False
            subscription.save()
        else:
            active_subscriptions.append(subscription)
    
    # Get subscription summary
    subscription_summary = UserSubscriptionManager.get_subscription_summary(request.user)
    
    # Debug logging
    logger.info(f"Payment plans view for user: {request.user.username}")
    logger.info(f"Found {visible_plans.count()} visible plans")
    logger.info(f"PayU Merchant Key: {settings.PAYU_MERCHANT_KEY}")
    logger.info(f"PayU Base URL: {settings.PAYU_BASE_URL}")
    logger.info(f"Base Domain: {settings.BASE_DOMAIN}")
    
    context = {
            'categorized_plans': categorized_plans,
            'user_subscriptions': active_subscriptions,
            'subscription_summary': subscription_summary,
            'total_plans': visible_plans.count(),
            'has_any_subscriptions': len(active_subscriptions) > 0,
            'csrf_token': get_token(request),
            'payu_base_url': settings.PAYU_BASE_URL,
            'payu_mode': settings.PAYU_MODE,  # ADD THIS LINE
            'debug_info': {
                'merchant_key': settings.PAYU_MERCHANT_KEY,
                'base_domain': settings.BASE_DOMAIN,
                'payu_mode': settings.PAYU_MODE
            }
    }
    
    return render(request, 'payments/plans.html', context)
    
@login_required
@require_http_methods(["POST"])
def initiate_payment(request):
    """Initialize PayU Bolt payment with enhanced debugging"""
    try:
        plan_uid = request.POST.get('plan_uid')
        logger.info(f"=== PAYMENT INITIATION START ===")
        logger.info(f"Plan UID: {plan_uid}")
        logger.info(f"User: {request.user.username}")
        logger.info(f"User Email: {request.user.email}")
        
        if not plan_uid:
            logger.error("Plan UID is missing")
            return JsonResponse({'success': False, 'error': 'Plan UID is required'})
        
        # Get the plan
        try:
            plan = PaymentPlan.objects.get(uid=plan_uid, is_active=True)
            logger.info(f"Plan found: {plan.name} - Price: {plan.price}")
        except PaymentPlan.DoesNotExist:
            logger.error(f"Plan not found: {plan_uid}")
            return JsonResponse({'success': False, 'error': 'Invalid plan selected'})
        
        # Clean up existing pending transactions
        existing_transactions = PaymentTransaction.objects.filter(
            user=request.user,
            plan=plan,
            status='pending',
            expires_at__gt=timezone.now()
        )
        
        if existing_transactions.exists():
            logger.info(f"Cleaning up {existing_transactions.count()} pending transactions")
            existing_transactions.update(status='cancelled')
        
        # Create new transaction
        transaction = PaymentTransaction.objects.create(
            user=request.user,
            plan=plan,
            transaction_id=uuid.uuid4().hex,
            amount=plan.price,
            status='pending',
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        
        logger.info(f"Created transaction: {transaction.transaction_id}")
        logger.info(f"Transaction amount: {transaction.amount}")
        
        # Prepare PayU data with proper error handling
        try:
            logger.info("=== PREPARING PAYU DATA ===")
            payu_data = prepare_payu_data(transaction, request.user)
            bolt_config = PayUBoltConfig.get_bolt_config(payu_data)
            
            logger.info("PayU data prepared successfully")
            logger.info(f"Hash generated: {payu_data['hash'][:20]}...")
            logger.info(f"Bolt config keys: {list(bolt_config.keys())}")
            
        except Exception as e:
            logger.error(f"Error preparing PayU data: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            transaction.status = 'failed'
            transaction.failure_reason = 'Configuration error'
            transaction.save()
            
            # Return detailed error for debugging
            return JsonResponse({
                'success': False, 
                'error': f'Payment configuration failed: {str(e)}'
            })
        
        response_data = {
            'success': True,
            'transaction_id': str(transaction.transaction_id),
            'bolt_config': bolt_config,
            'plan_name': plan.name,
            'amount': str(plan.price),
            'debug_info': {
                'has_surl': 'surl' in bolt_config,
                'has_furl': 'furl' in bolt_config,
                'config_keys': list(bolt_config.keys())
            }
        }
        
        logger.info(f"=== BOLT PAYMENT INITIATION SUCCESS ===")
        logger.info(f"Response keys: {list(response_data.keys())}")
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Unexpected error in payment initiation: {str(e)}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return JsonResponse({
            'success': False, 
            'error': f'Payment initialization failed: {str(e)}'
        })
@csrf_exempt
@require_http_methods(["POST"])
def payment_success(request):
    """Handle successful payment response from PayU"""
    try:
        response_data = request.POST.dict()
        logger.info(f"=== PAYMENT SUCCESS CALLBACK ===")
        logger.info(f"Response data: {response_data}")
        
        txnid = response_data.get('txnid')
        status = response_data.get('status')
        mihpayid = response_data.get('mihpayid')
        
        if not txnid:
            logger.error("Transaction ID missing")
            return HttpResponse("Transaction ID missing", status=400)
        
        # Get transaction
        try:
            transaction = PaymentTransaction.objects.get(transaction_id=txnid)
            logger.info(f"Transaction found: {txnid}")
        except PaymentTransaction.DoesNotExist:
            logger.error(f"Transaction not found: {txnid}")
            return HttpResponse("Transaction not found", status=404)
        
        # Verify hash
        received_hash = response_data.get('hash', '').lower()
        if received_hash:
            try:
                calculated_hash = verify_payment_hash(response_data, settings.PAYU_SALT)
                
                logger.info(f"Received hash: {received_hash}")
                logger.info(f"Calculated hash: {calculated_hash}")
                
                if received_hash != calculated_hash:
                    logger.error("Hash verification failed!")
                    transaction.status = 'failed'
                    transaction.failure_reason = 'Hash verification failed'
                    transaction.gateway_response = response_data
                    transaction.save()
                    return HttpResponse("Payment verification failed", status=400)
                else:
                    logger.info("Hash verification successful")
            except Exception as e:
                logger.error(f"Hash verification error: {str(e)}")
                return HttpResponse("Verification error", status=500)
        
        # Process successful payment
        if status and status.lower() == 'success':
            transaction.status = 'success'
            transaction.mihpayid = mihpayid
            transaction.gateway_response = response_data
            transaction.processed_at = timezone.now()
            transaction.save()
            
            logger.info(f"Payment successful for transaction: {txnid}")
            
            # Create subscription
            try:
                subscription = UserSubscriptionManager.process_new_subscription(
                    transaction.user, transaction
                )
                logger.info(f"Subscription created: {subscription.uid}")
                
                messages.success(request, f'Payment successful! Your {transaction.plan.name} subscription is now active.')
                return redirect('payments:plans')
                
            except Exception as e:
                logger.error(f"Error creating subscription: {str(e)}")
                return HttpResponse("Subscription creation failed", status=500)
        else:
            failure_reason = response_data.get('error_Message', f'Payment status: {status}')
            logger.warning(f"Payment failed: {failure_reason}")
            
            transaction.status = 'failed'
            transaction.failure_reason = failure_reason
            transaction.gateway_response = response_data
            transaction.save()
            
            messages.error(request, f'Payment failed: {failure_reason}')
            return redirect('payments:plans')
            
    except Exception as e:
        logger.error(f"Unexpected error in payment success: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return HttpResponse("Payment processing error", status=500)

@csrf_exempt
@require_http_methods(["POST"])
def payment_failure(request):
    """Handle failed payment response from PayU"""
    try:
        response_data = request.POST.dict()
        logger.info(f"=== PAYMENT FAILURE CALLBACK ===")
        logger.info(f"Failure response: {response_data}")
        
        txnid = response_data.get('txnid')
        error_message = response_data.get('error_Message', 'Payment failed')
        
        if txnid:
            try:
                transaction = PaymentTransaction.objects.get(transaction_id=txnid)
                transaction.status = 'failed'
                transaction.failure_reason = error_message
                transaction.gateway_response = response_data
                transaction.save()
                
                logger.info(f"Transaction marked as failed: {txnid}")
            except PaymentTransaction.DoesNotExist:
                logger.warning(f"Transaction not found in failure: {txnid}")
        
        messages.error(request, f'Payment failed: {error_message}')
        return redirect('payments:plans')
        
    except Exception as e:
        logger.error(f"Error processing payment failure: {str(e)}")
        return HttpResponse("Error processing failure", status=500)

@login_required
def check_payment_status(request, transaction_id):
    """Check payment status via AJAX"""
    try:
        transaction = PaymentTransaction.objects.get(
            transaction_id=transaction_id,
            user=request.user
        )
        
        response_data = {
            'success': True,
            'status': transaction.status,
            'mihpayid': transaction.mihpayid,
            'amount': str(transaction.amount),
            'created_at': transaction.created_at.isoformat(),
        }
        
        return JsonResponse(response_data)
        
    except PaymentTransaction.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Transaction not found'})
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Status check failed'})

@login_required
def check_payment_status(request, transaction_id):
    """Check payment status via AJAX"""
    try:
        transaction = PaymentTransaction.objects.get(
            transaction_id=transaction_id,
            user=request.user
        )
        
        logger.info(f"Status check for transaction {transaction_id}: {transaction.status}")
        
        response_data = {
            'success': True,
            'status': transaction.status,
            'mihpayid': transaction.mihpayid,
            'amount': str(transaction.amount),
            'created_at': transaction.created_at.isoformat(),
        }
        
        if transaction.status == 'success' and hasattr(transaction, 'subscription'):
            response_data['subscription_end'] = transaction.subscription.end_date.strftime('%B %d, %Y')
        
        return JsonResponse(response_data)
        
    except PaymentTransaction.DoesNotExist:
        logger.warning(f"Transaction not found for status check: {transaction_id}")
        return JsonResponse({'success': False, 'error': 'Transaction not found'})
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Status check failed'})


@csrf_exempt
@require_http_methods(["POST"])
def bolt_response(request):
    """Handle Bolt payment response - AJAX endpoint"""
    try:
        # Bolt sends JSON response
        import json
        response_data = json.loads(request.body.decode('utf-8'))
        
        logger.info(f"=== BOLT RESPONSE RECEIVED ===")
        logger.info(f"Bolt response: {response_data}")
        
        if 'response' in response_data:
            payment_response = response_data['response']
            txnid = payment_response.get('txnid')
            status = payment_response.get('status')
            
            if txnid:
                try:
                    transaction = PaymentTransaction.objects.get(transaction_id=txnid)
                    
                    if status == 'success':
                        transaction.status = 'success'
                        transaction.mihpayid = payment_response.get('mihpayid')
                        transaction.gateway_response = payment_response
                        transaction.processed_at = timezone.now()
                        transaction.save()
                        
                        # Create subscription
                        subscription = UserSubscriptionManager.process_new_subscription(
                            transaction.user, transaction
                        )
                        
                        return JsonResponse({
                            'success': True,
                            'message': 'Payment successful',
                            'subscription_id': str(subscription.uid)
                        })
                    else:
                        transaction.status = 'failed'
                        transaction.failure_reason = payment_response.get('error', 'Payment failed')
                        transaction.gateway_response = payment_response
                        transaction.save()
                        
                        return JsonResponse({
                            'success': False,
                            'error': payment_response.get('error', 'Payment failed')
                        })
                        
                except PaymentTransaction.DoesNotExist:
                    logger.error(f"Transaction not found: {txnid}")
                    return JsonResponse({'success': False, 'error': 'Transaction not found'})
        
        return JsonResponse({'success': False, 'error': 'Invalid response format'})
        
    except Exception as e:
        logger.error(f"Bolt response handling error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Response processing failed'})


# Add to views.py for testing
@login_required
def debug_payu(request):
    """Debug PayU configuration"""
    test_data = {
        'key': settings.PAYU_MERCHANT_KEY,
        'txnid': 'TEST123',
        'amount': '10.00',
        'productinfo': 'Test',
        'firstname': 'Test',
        'email': 'test@test.com',
        'udf1': '',
        'udf2': '',
        'udf3': '',
        'udf4': '',
        'udf5': ''
    }
    
    hash_val = generate_hash(test_data, settings.PAYU_SALT)
    
    return JsonResponse({
        'merchant_key': settings.PAYU_MERCHANT_KEY,
        'salt_length': len(settings.PAYU_SALT),
        'mode': settings.PAYU_MODE,
        'test_hash': hash_val[:20] + '...',
        'bolt_url': settings.PAYU_BOLT_URL
    })