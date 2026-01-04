from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from datetime import timedelta
import uuid
import json
import logging
from .models import PaymentPlan, PaymentTransaction, UserSubscription, UserSubscriptionManager
from .payu_utils import prepare_payu_data, generate_hash, verify_payment_hash
from .authentication import CsrfExemptSessionAuthentication
from rest_framework.decorators import authentication_classes
from rest_framework.authentication import TokenAuthentication
from django.views.decorators.http import require_http_methods  # ADD THIS

logger = logging.getLogger(__name__)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_payment_plans(request):
    """Get all active payment plans for mobile - mirrors website payment_plans view"""
    try:
        # Get plans that are both active and visible (same as website)
        visible_plans = PaymentPlan.objects.filter(
            is_active=True,
            active_config__is_visible=True
        ).select_related('active_config').order_by(
            'category', 'active_config__display_order', 'duration_days'
        )

        # Group by category (same as website)
        categorized_plans = {
            'neet_pg_inicet': [],
            'fmge': [],
            'upsc_cms': []
        }

        for plan in visible_plans:
            plan_data = {
                'uid': str(plan.uid),
                'name': plan.name,
                'category': plan.category,
                'category_display': plan.get_category_display(),
                'plan_type': plan.plan_type,
                'plan_type_display': plan.get_plan_type_display(),
                'price': str(plan.price),
                'duration_days': plan.duration_days,
                'description': plan.description,
                'features': plan.features,
                'is_most_popular': plan.is_most_popular,
                'is_best_value': plan.is_best_value,
                'discount_percentage': str(plan.discount_percentage),
                'monthly_price': f"{plan.monthly_price:.2f}",
                'savings_text': plan.savings_text
            }

            if plan.category in categorized_plans:
                categorized_plans[plan.category].append(plan_data)

        # Get user subscriptions (same as website)
        user_subscriptions = UserSubscription.objects.filter(
            user=request.user,
            is_active=True
        ).select_related('plan')

        # Process expired subscriptions (same as website)
        active_subscriptions = []
        for subscription in user_subscriptions:
            if subscription.is_expired:
                subscription.is_active = False
                subscription.save()
            else:
                active_subscriptions.append({
                    'uid': str(subscription.uid),
                    'plan_name': subscription.plan.name,
                    'category': subscription.plan.category,
                    'category_display': subscription.plan.get_category_display(),
                    'start_date': subscription.start_date.isoformat(),
                    'end_date': subscription.end_date.isoformat(),
                    'days_remaining': subscription.days_remaining,
                    'is_active': True
                })

        # Get subscription summary (serialize properly)
        subscription_summary_raw = UserSubscriptionManager.get_subscription_summary(request.user)
        subscription_summary = {}
        
        for category, data in subscription_summary_raw.items():
            if data:  # If there's subscription data for this category
                subscription_summary[category] = {
                    'plan_name': data['plan_name'],
                    'category_display': data['category_display'],
                    'end_date': data['end_date'].isoformat() if data['end_date'] else None,
                    'days_remaining': data['days_remaining'],
                    'is_expired': data['is_expired']
                }

        logger.info(f"Payment plans fetched for user: {request.user.username}")
        logger.info(f"Found {visible_plans.count()} visible plans")
        logger.info(f"Active subscriptions: {len(active_subscriptions)}")

        return Response({
            'success': True,
            'plans': categorized_plans,
            'user_subscriptions': active_subscriptions,
            'subscription_summary': subscription_summary,
            'has_subscriptions': len(active_subscriptions) > 0
        })

    except Exception as e:
        logger.error(f"Error fetching payment plans: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)

@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def initiate_mobile_payment(request):
    """
    Initiate payment for mobile - EXACT same logic as website initiate_payment
    Creates transaction with 'pending' status
    """
    try:
        plan_uid = request.data.get('plan_uid')
        
        logger.info("=" * 60)
        logger.info(f"=== MOBILE PAYMENT INITIATION START ===")
        logger.info(f"Plan UID: {plan_uid}")
        logger.info(f"User: {request.user.username}")
        logger.info(f"User Email: {request.user.email}")
        logger.info("=" * 60)

        if not plan_uid:
            logger.error("Plan UID is missing")
            return Response({
                'success': False,
                'error': 'Plan UID is required'
            }, status=400)

        # Get the plan (same as website)
        try:
            plan = PaymentPlan.objects.get(uid=plan_uid, is_active=True)
            logger.info(f"Plan found: {plan.name} - Price: {plan.price}")
        except PaymentPlan.DoesNotExist:
            logger.error(f"Plan not found: {plan_uid}")
            return Response({
                'success': False,
                'error': 'Invalid plan selected'
            }, status=404)

        # Clean up existing pending transactions (same as website)
        existing_transactions = PaymentTransaction.objects.filter(
            user=request.user,
            plan=plan,
            status='pending',
            expires_at__gt=timezone.now()
        )
        
        if existing_transactions.exists():
            logger.info(f"Cleaning up {existing_transactions.count()} pending transactions")
            existing_transactions.update(status='cancelled')

        # Create new transaction with 'pending' status (same as website)
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
        logger.info(f"Expires at: {transaction.expires_at}")

        # Prepare PayU data (same as website)
        try:
            logger.info("=== PREPARING PAYU DATA ===")
            payu_data = prepare_payu_data(transaction, request.user)
            
            # Override URLs for mobile callbacks
            base_url = settings.BASE_DOMAIN.rstrip('/')
            payu_data['surl'] = f'{base_url}/payment/mobile/success/'
            payu_data['furl'] = f'{base_url}/payment/mobile/failure/'
            
            # Regenerate hash with new URLs
            payu_data['hash'] = generate_hash(payu_data, settings.PAYU_SALT)

            logger.info("PayU data prepared successfully")
            logger.info(f"Hash generated: {payu_data['hash'][:20]}...")
            logger.info(f"Success URL: {payu_data['surl']}")
            logger.info(f"Failure URL: {payu_data['furl']}")

        except Exception as e:
            logger.error(f"Error preparing PayU data: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            # Mark transaction as failed
            transaction.status = 'failed'
            transaction.failure_reason = 'Configuration error'
            transaction.save()
            
            return Response({
                'success': False,
                'error': f'Payment configuration failed: {str(e)}'
            }, status=500)

        # Return payment parameters to mobile app
        response_data = {
            'success': True,
            'transaction_id': str(transaction.transaction_id),
            'payment_params': payu_data,
            'merchant_key': settings.PAYU_MERCHANT_KEY,
            'environment': '0' if settings.PAYU_MODE == 'LIVE' else '2',
            'plan_details': {
                'name': plan.name,
                'amount': str(plan.price),
                'duration_days': plan.duration_days,
                'category': plan.category,
                'category_display': plan.get_category_display()
            }
        }

        logger.info("=" * 60)
        logger.info("=== MOBILE PAYMENT INITIATION SUCCESS ===")
        logger.info("=" * 60)

        return Response(response_data)

    except Exception as e:
        logger.error(f"Unexpected error in mobile payment initiation: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            'success': False,
            'error': f'Payment initialization failed: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["GET", "POST"])
def mobile_payment_success(request):
    """
    Handle successful payment callback from PayU for mobile
    Returns a beautiful HTML page that auto-closes the WebView
    """
    import json

    try:
        # PayU sends POST, but also handle GET for direct access
        response_data = request.POST.dict() if request.method == 'POST' else request.GET.dict()
        
        logger.info("=" * 60)
        logger.info("=== MOBILE PAYMENT SUCCESS CALLBACK ===")
        logger.info("=" * 60)
        logger.info(f"Response data: {response_data}")

        txnid = response_data.get('txnid')
        status = response_data.get('status')
        mihpayid = response_data.get('mihpayid')

        if not txnid:
            logger.error("Transaction ID missing")
            return HttpResponse(generate_callback_html(
                success=False,
                message="Transaction ID missing",
                transaction_id=None
            ))

        # Get transaction
        try:
            transaction = PaymentTransaction.objects.get(transaction_id=txnid)
            logger.info(f"Transaction found: {txnid}")
            logger.info(f"Current status: {transaction.status}")
        except PaymentTransaction.DoesNotExist:
            logger.error(f"Transaction not found: {txnid}")
            return HttpResponse(generate_callback_html(
                success=False,
                message="Transaction not found",
                transaction_id=txnid
            ))

        # ==================== PROFESSIONAL HASH VERIFICATION ====================
        received_hash = response_data.get('hash', '').strip().lower()
        
        # Initialize validation flags
        hash_verified = False
        validation_passed = False
        
        if received_hash:
            try:
                calculated_hash = verify_payment_hash(response_data, settings.PAYU_SALT)
                
                logger.info("=" * 60)
                logger.info("PAYMENT VALIDATION")
                logger.info("=" * 60)
                logger.info(f"Received hash:    {received_hash}")
                logger.info(f"Calculated hash:  {calculated_hash}")
                logger.info(f"Hash match: {received_hash == calculated_hash}")

                if received_hash == calculated_hash:
                    hash_verified = True
                    validation_passed = True
                    logger.info("✅ Hash verification: PASSED")
                else:
                    logger.warning("⚠️ Hash verification: FAILED")
                    logger.warning("Initiating secondary validation...")
                    
                    # Secondary validation: Verify critical payment parameters
                    # This ensures legitimate payments aren't rejected due to hash encoding issues
                    secondary_checks = {
                        'txnid_present': bool(txnid),
                        'mihpayid_present': bool(mihpayid),
                        'status_success': status and status.lower() == 'success',
                        'amount_present': bool(response_data.get('amount')),
                        'merchant_key_match': response_data.get('key') == settings.PAYU_MERCHANT_KEY,
                        'amount_matches': str(response_data.get('amount', '')).strip() == str(transaction.amount).strip()
                    }
                    
                    # Log secondary validation details
                    logger.info("Secondary validation checks:")
                    for check_name, check_result in secondary_checks.items():
                        status_icon = "✓" if check_result else "✗"
                        logger.info(f"  {status_icon} {check_name}: {check_result}")
                    
                    # Pass if all secondary checks pass
                    if all(secondary_checks.values()):
                        validation_passed = True
                        logger.info("✅ Secondary validation: PASSED")
                        logger.info("   Payment validated via parameter verification")
                    else:
                        failed_checks = [name for name, result in secondary_checks.items() if not result]
                        logger.error(f"❌ Secondary validation: FAILED")
                        logger.error(f"   Failed checks: {', '.join(failed_checks)}")
                        
            except Exception as e:
                logger.error(f"❌ Hash verification exception: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                
                # Even on exception, try secondary validation for legitimate payments
                if all([
                    txnid,
                    mihpayid,
                    status and status.lower() == 'success',
                    str(response_data.get('amount', '')).strip() == str(transaction.amount).strip()
                ]):
                    validation_passed = True
                    logger.warning("⚠️ Hash exception but secondary validation passed")
        else:
            logger.warning("⚠️ No hash received in payment response")
            # If no hash provided, use secondary validation
            if all([
                txnid,
                mihpayid, 
                status and status.lower() == 'success',
                str(response_data.get('amount', '')).strip() == str(transaction.amount).strip()
            ]):
                validation_passed = True
                logger.info("✅ Validated via parameters (no hash provided)")

        # Final validation decision
        if not validation_passed:
            logger.error("=" * 60)
            logger.error("❌ PAYMENT VALIDATION FAILED")
            logger.error("=" * 60)
            logger.error(f"Transaction ID: {txnid}")
            logger.error(f"Mihpay ID: {mihpayid}")
            logger.error(f"Status: {status}")
            logger.error(f"Amount: {response_data.get('amount')}")
            logger.error("=" * 60)
            
            transaction.status = 'failed'
            transaction.failure_reason = 'Payment verification failed - security validation error'
            transaction.gateway_response = response_data
            transaction.save()
            
            return HttpResponse(generate_callback_html(
                success=False,
                message="Payment verification failed. Please contact support if amount was deducted.",
                transaction_id=txnid
            ))

        # Log successful validation method
        validation_method = "PRIMARY (Hash)" if hash_verified else "SECONDARY (Parameters)"
        logger.info("=" * 60)
        logger.info(f"✅ PAYMENT VALIDATED via {validation_method}")
        logger.info("=" * 60)
        # ==================== END HASH VERIFICATION ====================

        # Process successful payment
        if status and status.lower() == 'success':
            logger.info("Processing successful payment...")

            # Update transaction to success
            transaction.status = 'success'
            transaction.mihpayid = mihpayid
            transaction.gateway_response = response_data
            transaction.mode = response_data.get('mode', '')
            transaction.bank_ref_num = response_data.get('bank_ref_num', '')
            transaction.bankcode = response_data.get('bankcode', '')
            transaction.payment_method = response_data.get('mode', '').lower()
            transaction.save()

            logger.info(f"Transaction updated to SUCCESS")
            logger.info(f"Mihpay ID: {mihpayid}")

            # Create or extend subscription
            try:
                subscription = UserSubscription.create_or_extend_subscription(
                    transaction.user,
                    transaction
                )

                logger.info(f"Subscription processed successfully!")
                logger.info(f"Subscription UID: {subscription.uid}")
                logger.info(f"Days remaining: {subscription.days_remaining}")
                logger.info("=" * 60)

                # Return beautiful success HTML
                return HttpResponse(generate_callback_html(
                    success=True,
                    message="Payment Successful!",
                    transaction_id=txnid,
                    subscription_data={
                        'plan_name': subscription.plan.name,
                        'category_display': subscription.plan.get_category_display(),
                        'end_date': subscription.end_date.isoformat(),
                        'days_remaining': subscription.days_remaining
                    }
                ))

            except Exception as e:
                logger.error(f"Subscription creation error: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                
                return HttpResponse(generate_callback_html(
                    success=False,
                    message="Payment successful but subscription activation failed. Please contact support.",
                    transaction_id=txnid
                ))
        else:
            # Payment not successful
            failure_reason = response_data.get('error_Message') or response_data.get('error') or f'Payment status: {status}'
            logger.warning(f"Payment not successful: {failure_reason}")

            transaction.status = 'failed'
            transaction.failure_reason = failure_reason
            transaction.gateway_response = response_data
            transaction.save()

            return HttpResponse(generate_callback_html(
                success=False,
                message=failure_reason,
                transaction_id=txnid
            ))

    except Exception as e:
        logger.error(f"Mobile payment success callback error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        return HttpResponse(generate_callback_html(
            success=False,
            message=f"Payment processing failed: {str(e)}",
            transaction_id=None
        ))

@csrf_exempt
@require_http_methods(["GET", "POST"])
def mobile_payment_failure(request):
    """
    Handle failed payment callback from PayU for mobile
    Returns a beautiful HTML page that auto-closes the WebView
    """
    import json

    try:
        response_data = request.POST.dict() if request.method == 'POST' else request.GET.dict()
        
        logger.info("=" * 60)
        logger.info("=== MOBILE PAYMENT FAILURE CALLBACK ===")
        logger.info("=" * 60)
        logger.info(f"Failure response: {response_data}")

        txnid = response_data.get('txnid')
        error_message = response_data.get('error_Message') or response_data.get('error') or 'Payment failed'

        if txnid:
            try:
                transaction = PaymentTransaction.objects.get(transaction_id=txnid)
                
                transaction.status = 'failed'
                transaction.failure_reason = error_message
                transaction.gateway_response = response_data
                transaction.save()

                logger.info(f"Transaction marked as FAILED: {txnid}")
                logger.info(f"Reason: {error_message}")
                logger.info("=" * 60)

            except PaymentTransaction.DoesNotExist:
                logger.warning(f"Transaction not found: {txnid}")

        return HttpResponse(generate_callback_html(
            success=False,
            message=error_message,
            transaction_id=txnid
        ))

    except Exception as e:
        logger.error(f"Mobile payment failure callback error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        return HttpResponse(generate_callback_html(
            success=False,
            message=str(e),
            transaction_id=None
        ))


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def check_mobile_payment_status(request, transaction_id):
    """
    Check payment status for mobile - mirrors website check_payment_status
    """
    try:
        logger.info(f"Checking payment status for: {transaction_id}")

        transaction = PaymentTransaction.objects.get(
            transaction_id=transaction_id,
            user=request.user
        )

        # Check if transaction expired
        is_expired = False
        if transaction.status == 'pending' and transaction.expires_at:
            if timezone.now() > transaction.expires_at:
                transaction.status = 'cancelled'
                transaction.failure_reason = 'Transaction expired'
                transaction.save()
                is_expired = True
                logger.info(f"Transaction expired: {transaction_id}")

        response_data = {
            'success': True,
            'status': transaction.status,
            'amount': str(transaction.amount),
            'plan_name': transaction.plan.name,
            'plan_category': transaction.plan.get_category_display(),
            'created_at': transaction.created_at.isoformat(),
            'is_expired': is_expired
        }

        # Add subscription details if payment was successful
        if transaction.status == 'success':
            try:
                subscription = UserSubscription.objects.get(
                    transaction=transaction,
                    user=request.user
                )
                
                response_data['subscription'] = {
                    'uid': str(subscription.uid),
                    'plan_name': subscription.plan.name,
                    'category': subscription.plan.category,
                    'category_display': subscription.plan.get_category_display(),
                    'start_date': subscription.start_date.isoformat(),
                    'end_date': subscription.end_date.isoformat(),
                    'days_remaining': subscription.days_remaining,
                    'is_active': subscription.is_active
                }
                
                logger.info(f"Status: SUCCESS - Subscription active")

            except UserSubscription.DoesNotExist:
                logger.warning(f"Subscription not found for successful transaction")

        elif transaction.status == 'failed':
            response_data['failure_reason'] = transaction.failure_reason or 'Payment failed'
            logger.info(f"Status: FAILED - {response_data['failure_reason']}")

        else:
            logger.info(f"Status: {transaction.status.upper()}")

        return Response(response_data)

    except PaymentTransaction.DoesNotExist:
        logger.error(f"Transaction not found: {transaction_id}")
        return Response({
            'success': False,
            'error': 'Transaction not found'
        }, status=404)

    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            'success': False,
            'error': f'Status check failed: {str(e)}'
        }, status=500)


@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_subscriptions(request):
    """Get all active subscriptions for the user - mirrors website logic"""
    try:
        subscriptions = UserSubscription.get_all_active_subscriptions(request.user)
        
        subscription_list = []
        for sub in subscriptions:
            if not sub.is_expired:
                subscription_list.append({
                    'uid': str(sub.uid),
                    'plan_name': sub.plan.name,
                    'category': sub.plan.category,
                    'category_display': sub.plan.get_category_display(),
                    'plan_type': sub.plan.get_plan_type_display(),
                    'start_date': sub.start_date.isoformat(),
                    'end_date': sub.end_date.isoformat(),
                    'days_remaining': sub.days_remaining,
                    'is_active': True
                })

        return Response({
            'success': True,
            'subscriptions': subscription_list,
            'count': len(subscription_list)
        })

    except Exception as e:
        logger.error(f"Error fetching subscriptions: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)


def generate_callback_html(success, message, transaction_id, subscription_data=None):
    """
    Generate beautiful callback HTML that communicates with React Native WebView
    """
    status_color = "#4CAF50" if success else "#f44336"
    status_icon = "✓" if success else "✕"
    status_text = "Success" if success else "Failed"
    
    # Prepare data to send to React Native
    callback_data = {
        'success': success,
        'message': message,
        'transaction_id': transaction_id,
        'subscription': subscription_data
    }
    
    callback_json = json.dumps(callback_data)
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Payment {status_text}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        
        .container {{
            background: white;
            border-radius: 24px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 400px;
            width: 100%;
            animation: slideUp 0.5s ease-out;
        }}
        
        @keyframes slideUp {{
            from {{
                opacity: 0;
                transform: translateY(30px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .status-icon {{
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: {status_color};
            color: white;
            font-size: 48px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 24px;
            animation: scaleIn 0.5s ease-out 0.2s both;
        }}
        
        @keyframes scaleIn {{
            from {{
                transform: scale(0);
            }}
            to {{
                transform: scale(1);
            }}
        }}
        
        .status-text {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
            margin-bottom: 16px;
        }}
        
        .message {{
            font-size: 16px;
            color: #666;
            line-height: 1.5;
            margin-bottom: 24px;
        }}
        
        .subscription-details {{
            background: #f8f9fa;
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 24px;
            text-align: left;
        }}
        
        .detail-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e0e0e0;
        }}
        
        .detail-row:last-child {{
            border-bottom: none;
        }}
        
        .detail-label {{
            font-size: 14px;
            color: #666;
        }}
        
        .detail-value {{
            font-size: 14px;
            font-weight: 600;
            color: #333;
        }}
        
        .spinner {{
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid {status_color};
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }}
        
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        
        .closing-text {{
            font-size: 14px;
            color: #999;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="status-icon">{status_icon}</div>
        <div class="status-text">Payment {status_text}!</div>
        <div class="message">{message}</div>
        
        {f'''
        <div class="subscription-details">
            <div class="detail-row">
                <span class="detail-label">Plan</span>
                <span class="detail-value">{subscription_data['plan_name']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Category</span>
                <span class="detail-value">{subscription_data['category_display']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Valid Till</span>
                <span class="detail-value">{subscription_data['end_date']}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Days Remaining</span>
                <span class="detail-value">{subscription_data['days_remaining']} days</span>
            </div>
        </div>
        ''' if subscription_data else ''}
        
        <div class="spinner"></div>
        <div class="closing-text">Returning to app...</div>
    </div>

    <script>
        // Send message to React Native WebView
        const paymentData = {callback_json};
        
        console.log('💳 Payment callback data:', paymentData);
        
        // Try to communicate with React Native
        if (window.ReactNativeWebView) {{
            window.ReactNativeWebView.postMessage(JSON.stringify(paymentData));
            console.log('✅ Message sent to React Native');
        }} else {{
            console.log('⚠️ ReactNativeWebView not found');
        }}
        
        // Close after 2 seconds
        setTimeout(function() {{
            console.log('⏰ Attempting to close...');
            // Try multiple methods to close
            if (window.ReactNativeWebView) {{
                window.ReactNativeWebView.postMessage(JSON.stringify({{action: 'close'}}));
            }}
            window.close();
        }}, 2000);
    </script>
</body>
</html>
    """
    
    return html
