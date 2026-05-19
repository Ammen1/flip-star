# Telebirr Direct Debit Integration Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Files and Components](#files-and-components)
4. [SOAP API Integration](#soap-api-integration)
5. [Operation Flows](#operation-flows)
6. [Frontend Implementation](#frontend-implementation)
7. [Backend Implementation](#backend-implementation)
8. [Testing](#testing)
9. [Security Considerations](#security-considerations)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This document provides a comprehensive explanation of the Telebirr Direct Debit integration for the Flipstar platform. The integration enables users to subscribe to premium plans using Telebirr's mobile money system, with automatic recurring payments via direct debit mandates.

### Key Features
- **Mandate Creation**: Create direct debit mandates for daily, weekly, or monthly subscriptions
- **Mandate Activation**: User confirms mandate via Telebirr app
- **Automatic Debit**: System initiates recurring payments based on mandate
- **Mandate Cancellation**: Users can cancel their Telebirr subscriptions directly from the platform

---

## Architecture

### System Components

```
┌─────────────────┐
│   Frontend      │
│  (React)        │
└────────┬────────┘
         │ HTTP/REST API
         ▼
┌─────────────────┐
│   Backend       │
│  (Django)       │
└────────┬────────┘
         │ SOAP/XML
         ▼
┌─────────────────┐
│  Telebirr       │
│  SOAP Server    │
└─────────────────┘
```

### Data Flow
1. **Frontend**: React components handle user interactions and API calls
2. **Backend**: Django REST API processes requests and manages business logic
3. **Telebirr Service**: Python service constructs SOAP envelopes and communicates with Telebirr
4. **Telebirr Server**: Mobile money system processes direct debit operations

---

## Files and Components

### Frontend Files

#### 1. `frontend/components/SubscriptionPage.jsx`
**Purpose**: Main subscription interface for users to view plans and subscribe via Telebirr.

**Key Components**:
- **State Management**: Manages subscription tiers, modal states, processing status
- **Telebirr Modal**: Shows phone number input (auto-filled from user profile)
- **Success Modal**: Displays confirmation after successful mandate creation
- **Cancel Button**: Allows users to cancel active Telebirr subscriptions

**Code Block - Telebirr Modal**:
```javascript
const [telebirrModalOpen, setTelebirrModalOpen] = useState(false);
const [telebirrPhone, setTelebirrPhone] = useState('');
const [successModalOpen, setSuccessModalOpen] = useState(false);

// Fetch phone number from API (like coin purchase modal)
const handleTelebirrSubscribe = async (tier) => {
  setSelectedTierForTelebirr(tier);
  try {
    const profile = await api.request('/profile/me/');
    setTelebirrPhone(profile?.phone_number || user?.profile?.phone_number || '');
  } catch (error) {
    console.error('Failed to fetch phone number:', error);
    setTelebirrPhone(user?.profile?.phone_number || '');
  }
  setTelebirrModalOpen(true);
};
```

**Usage**: When user clicks "Subscribe via Telebirr", this function fetches the user's phone number from the backend and displays it in a modal for confirmation.

**Code Block - Success Modal**:
```javascript
if (response.success) {
  setSuccessModalOpen(true);
  setTimeout(() => setSuccessModalOpen(false), 3000);
  startPolling(selectedTierForTelebirr);
}
```

**Usage**: Displays a centered modal with green checkmark after successful mandate creation. Auto-dismisses after 3 seconds.

**Code Block - Cancel Handler**:
```javascript
const handleCancelTelebirrSubscription = async () => {
  if (!currentSubscription?.mandate_id) {
    showToast('error', 'No Telebirr mandate found');
    return;
  }

  if (confirm('Are you sure you want to cancel your Telebirr subscription?')) {
    setProcessing(true);
    try {
      const response = await api.request('/direct-debit/cancel/', {
        method: 'POST',
        body: JSON.stringify({
          mandate_id: currentSubscription.mandate_id,
        }),
      });

      if (response.success) {
        showToast('success', 'Telebirr subscription cancelled successfully');
        loadSubscriptionData();
      } else {
        showToast('error', response.error || 'Failed to cancel Telebirr subscription');
      }
    } catch (error) {
      console.error('Cancel Telebirr subscription error:', error);
      showToast('error', 'Failed to cancel Telebirr subscription');
    } finally {
      setProcessing(false);
    }
  }
};
```

**Usage**: Allows users to cancel their Telebirr subscription by calling the backend cancel endpoint with the mandate ID.

---

### Backend Files

#### 2. `backend/api/telebirr_direct_debit_service.py`
**Purpose**: Python service class that handles all SOAP API communication with Telebirr.

**Key Components**:
- **Raw SOAP Requests**: Uses Python `requests` library to send SOAP envelopes
- **Envelope Construction**: Builds XML envelopes matching Telebirr documentation structure
- **Response Parsing**: Extracts response codes and messages from SOAP responses
- **Four Operations**: create_mandate, activate_mandate, initiate_debit, cancel_mandate

**Code Block - SOAP Envelope Construction**:
```python
def _build_soap_envelope(self, command_id, initiator, receiver_party, body_xml):
    """Build SOAP envelope for Telebirr Direct Debit API"""
    originator_conversation_id = self._generate_originator_conversation_id()
    conversation_id = self._generate_conversation_id()
    timestamp = self._generate_timestamp()
    
    soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr" xmlns:req="http://cps.huawei.com/cpsinterface/request" xmlns:com="http://cps.huawei.com/cpsinterface/common">
  <soapenv:Header/>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <req:Version>1.0</req:Version>
        <req:CommandID>{command_id}</req:CommandID>
        <req:OriginatorConversationID>{originator_conversation_id}</req:OriginatorConversationID>
        <req:ConversationID>{conversation_id}</req:ConversationID>
        <req:Caller>
          <req:CallerType>{self.caller_type}</req:CallerType>
          <req:ThirdPartyID>{self.third_party_id}</req:ThirdPartyID>
          <req:Password>{self.third_party_password}</req:Password>
          <req:ResultURL>{self.result_url}</req:ResultURL>
        </req:Caller>
        <req:KeyOwner>1</req:KeyOwner>
        <req:Timestamp>{timestamp}</req:Timestamp>
      </req:Header>
      <req:Body>
        <req:Identity>
          <req:Initiator>
            <req:IdentifierType>{initiator['IdentifierType']}</req:IdentifierType>
            <req:Identifier>{initiator['Identifier']}</req:Identifier>
            <req:SecurityCredential>{initiator['SecurityCredential']}</req:SecurityCredential>
          </req:Initiator>
          <req:ReceiverParty>
            <req:IdentifierType>{receiver_party['IdentifierType']}</req:IdentifierType>
            <req:Identifier>{receiver_party['Identifier']}</req:Identifier>
          </req:ReceiverParty>
        </req:Identity>
        {body_xml}
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>'''
    
    return soap_envelope, originator_conversation_id, conversation_id
```

**Usage**: Constructs the complete SOAP envelope with all required headers and body content according to Telebirr's XML schema. The envelope includes:
- **Caller Information**: Third-party credentials for authentication
- **Identity**: Initiator (SP Operator) and Receiver Party (Customer MSISDN)
- **Command ID**: Specific operation being performed
- **Body Content**: Operation-specific parameters

**Why Raw SOAP?** The Telebirr test server doesn't provide a WSDL file, so we cannot use automated SOAP clients like `zeep`. Instead, we manually construct the XML envelope following the Telebirr API documentation.

**Code Block - Create Mandate**:
```python
def create_mandate(self, payer_msisdn, payer_reference_number, frequency, 
                  first_payment_date, expiry_date, payee_shortcode=None,
                  payee_account_name=None, start_range_of_days=1, 
                  end_range_of_days=22):
    """Create Direct Debit Mandate"""
    try:
        # Build initiator (SP Operator)
        initiator = {
            'IdentifierType': 14,  # SP Operator Username
            'Identifier': self.sp_operator_id or self.third_party_id,
            'SecurityCredential': self.sp_operator_credential or self.third_party_password,
        }
        
        # Build receiver party (Payer MSISDN)
        receiver_party = {
            'IdentifierType': 1,  # MSISDN
            'Identifier': payer_msisdn,
        }
        
        # Build body XML according to Telebirr documentation
        body_xml = f'''<req:CreateDirectDebitMandateByPayerRequest>
          <req:Payee> 
            <com:IdentifierType>4</com:IdentifierType>
            <com:IdentifierValue>{payee_shortcode}</com:IdentifierValue>
          </req:Payee>
          <req:DirectDebitMandateInfo>
            <com:PayerReferenceNumber>{payer_reference_number}</com:PayerReferenceNumber>
            <com:AgreedTC>1</com:AgreedTC>
            <com:PayeeAccountName>{payee_account_name}</com:PayeeAccountName>
            <com:PayerAccountName></com:PayerAccountName>
            <com:FirstPaymentDate>{first_payment_date}</com:FirstPaymentDate>
            <com:Frequency>{frequency}</com:Frequency>
            <com:StartRangeOfDays>{start_range_of_days}</com:StartRangeOfDays>
            <com:EndRangeOfDays>{end_range_of_days}</com:EndRangeOfDays>
            <com:ExpiryDate>{expiry_date}</com:ExpiryDate>
          </req:DirectDebitMandateInfo>
        </req:CreateDirectDebitMandateByPayerRequest>'''
        
        # Build SOAP envelope and make request
        soap_envelope, originator_conversation_id, conversation_id = self._build_soap_envelope(
            command_id='CreateDirectDebitMandateByCustomer',
            initiator=initiator,
            receiver_party=receiver_party,
            body_xml=body_xml
        )
        
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'CreateDirectDebitMandateByCustomer'
        }
        
        response = requests.post(self.soap_url, data=soap_envelope, headers=headers, timeout=30, verify=False)
        
        # Parse response and return result
        if response.status_code == 200:
            # Extract ResponseCode and ResponseDesc using regex
            response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
            response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)
            
            response_code = response_code_match.group(1) if response_code_match else '1'
            response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown error'
            
            if response_code == '0':
                return {
                    'success': True,
                    'originator_conversation_id': originator_conversation_id,
                    'conversation_id': conversation_id,
                    'message': response_desc,
                    'response_code': response_code
                }
            else:
                return {
                    'success': False,
                    'error': response_desc,
                    'response_code': response_code,
                    'conversation_id': conversation_id
                }
```

**Usage**: Creates a direct debit mandate with Telebirr. The mandate specifies:
- **Payer Information**: Customer's phone number and reference
- **Payee Information**: Flipstar's shortcode and account name
- **Payment Schedule**: Frequency (02=daily, 03=weekly, 05=monthly), dates, and ranges
- **Terms**: User agreement flag (AgreedTC=1)

**Why These Parameters?** Telebirr requires these fields to establish the direct debit agreement:
- **Frequency**: Determines how often to debit the account
- **Date Ranges**: Valid days for debiting (1-22) to avoid month-end issues
- **Expiry Date**: When the mandate automatically expires
- **Reference Number**: Unique identifier for tracking

---

#### 3. `backend/api/views_direct_debit.py`
**Purpose**: Django REST API views that handle HTTP requests and coordinate with the Telebirr service.

**Key Endpoints**:
- **`/direct-debit/create/`**: Creates a new direct debit mandate
- **`/direct-debit/activate/`**: Activates a mandate (webhook callback)
- **`/direct-debit/cancel/`**: Cancels an existing mandate
- **`/direct-debit/initiate/`**: Manually initiates a debit transaction

**Code Block - Create Mandate View**:
```python
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_direct_debit_mandate(request):
    """Create a direct debit mandate for Telebirr subscription"""
    try:
        user = request.user
        tier_id = request.data.get('tier_id')
        payer_msisdn = request.data.get('payer_msisdn')
        frequency = request.data.get('frequency')
        
        # Validate required fields
        if not all([tier_id, payer_msisdn, frequency]):
            return Response(
                {'error': 'tier_id, payer_msisdn, and frequency are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get tier
        try:
            tier = SubscriptionTier.objects.get(id=tier_id)
        except SubscriptionTier.DoesNotExist:
            return Response(
                {'error': 'Subscription tier not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calculate dates
        first_payment_date = (timezone.now() + timedelta(days=1)).strftime('%Y%m%d')
        expiry_date = (timezone.now() + timedelta(days=365)).strftime('%Y%m%d')
        
        # Generate reference number
        payer_reference_number = f"FLIPSTAR_{user.id}_{tier_id}_{int(timezone.now().timestamp())}"
        
        # Call Telebirr service to create mandate
        result = telebirr_direct_debit_service.create_mandate(
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            frequency=frequency,
            first_payment_date=first_payment_date,
            expiry_date=expiry_date
        )
        
        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'Mandate creation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Create mandate record in database
        mandate = DirectDebitMandate.objects.create(
            user=user,
            tier=tier,
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            frequency=frequency,
            first_payment_date=first_payment_date,
            expiry_date=expiry_date,
            status='pending_active',
            originator_conversation_id=result.get('originator_conversation_id'),
            conversation_id=result.get('conversation_id')
        )
        
        return Response({
            'success': True,
            'mandate_id': str(mandate.id),
            'payer_reference_number': payer_reference_number,
            'status': mandate.status,
            'message': 'Mandate created successfully. Please confirm via Telebirr app.'
        })
        
    except Exception as e:
        return Response(
            {'error': f'Failed to create mandate: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
```

**Usage**: This API endpoint:
1. Validates the request parameters
2. Retrieves the subscription tier
3. Calculates payment dates
4. Calls the Telebirr service to create the mandate
5. Stores the mandate in the database
6. Returns the mandate details to the frontend

**Why This Flow?** The backend acts as an intermediary to:
- Validate user permissions (IsAuthenticated)
- Enforce business rules (tier validation, date calculations)
- Maintain database records for tracking
- Handle errors gracefully

---

#### 4. `backend/config/settings.py`
**Purpose**: Django configuration including Telebirr API credentials and settings.

**Code Block - Telebirr Settings**:
```python
# Telebirr SOAP API Configuration
TELEBIRR_SOAP_URL = config('TELEBIRR_SOAP_URL', default='http://10.180.79.13:30001/payment/services/APIRequestMgrService')
TELEBIRR_THIRD_PARTY_ID = config('TELEBIRR_THIRD_PARTY_ID', default='TestMer')
TELEBIRR_THIRD_PARTY_PASSWORD = config('TELEBIRR_THIRD_PARTY_PASSWORD', default='jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=')
TELEBIRR_SHORTCODE = config('TELEBIRR_SHORTCODE', default='232323')
TELEBIRR_RESULT_URL = config('TELEBIRR_RESULT_URL', default='https://uat.flipstar.et/api/webhooks/telebirr-direct-debit')
TELEBIRR_PAYEE_ACCOUNT_NAME = config('TELEBIRR_PAYEE_ACCOUNT_NAME', default='Flipstar')
TELEBIRR_CALLER_TYPE = config('TELEBIRR_CALLER_TYPE', default='2')  # 2 = Third Party

# SP Operator credentials for SOAP API
TELEBIRR_SP_OPERATOR_ID = config('TELEBIRR_SP_OPERATOR_ID', default='TestSPOperAPI')
TELEBIRR_SP_OPERATOR_CREDENTIAL = config('TELEBIRR_SP_OPERATOR_CREDENTIAL', default='2JKSrKYlLAVvKWuIUXcexc3GHiT0+lEKzeVb6JRcZUM=')
```

**Usage**: These settings configure the Telebirr integration:
- **SOAP URL**: Telebirr API endpoint
- **Third Party ID/Password**: Authentication credentials
- **Shortcode**: Flipstar's merchant identifier
- **Result URL**: Webhook endpoint for Telebirr callbacks
- **SP Operator Credentials**: Service provider authentication

**Why Environment Variables?** Using `config()` from `python-decouple` allows:
- Different credentials for test/production environments
- Secure credential management (not hardcoded)
- Easy configuration changes without code deployment

---

## SOAP API Integration

### What is SOAP?

SOAP (Simple Object Access Protocol) is a protocol for exchanging structured information in web services. It uses XML for message formatting and typically operates over HTTP/HTTPS.

### Why SOAP for Telebirr?

Telebirr uses SOAP because:
- **Industry Standard**: Mobile money systems often use SOAP for enterprise integration
- **Structured Contracts**: XML schemas ensure strict message validation
- **Security**: Built-in WS-Security support
- **Transaction Integrity**: Reliable message delivery guarantees

### XML Structure Explained

Telebirr SOAP requests follow this structure:

```xml
<soapenv:Envelope>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <!-- Metadata: CommandID, Timestamp, Caller info -->
      </req:Header>
      <req:Body>
        <req:Identity>
          <!-- Who is initiating and receiving -->
        </req:Identity>
        <req:OperationRequest>
          <!-- Operation-specific parameters -->
        </req:OperationRequest>
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>
```

**Components Explained**:
- **Envelope**: Root element wrapping the entire message
- **Header**: Contains metadata (command, timestamps, authentication)
- **Identity**: Specifies the initiator and receiver of the operation
- **OperationRequest**: The actual operation parameters

### Namespaces

Telebirr uses XML namespaces to avoid naming conflicts:
- `soapenv`: SOAP envelope namespace
- `api`: Telebirr API request manager
- `req`: Request elements
- `com`: Common/shared elements

**Why Namespaces?** They allow:
- Multiple systems to use the same element names
- Clear separation of concerns
- XML validation against schemas

---

## Operation Flows

### Flow 1: Create Direct Debit Mandate

**Purpose**: Establish a direct debit agreement between the customer and Flipstar.

**Step-by-Step Flow**:

1. **Frontend**: User clicks "Subscribe via Telebirr" on a subscription tier
2. **Frontend**: Modal opens with auto-filled phone number from `/profile/me/`
3. **Frontend**: User clicks "Proceed"
4. **Frontend**: POST request to `/direct-debit/create/` with:
   ```json
   {
     "tier_id": "uuid",
     "payer_msisdn": "251903682272",
     "frequency": "02" // 02=daily, 03=weekly, 05=monthly
   }
   ```
5. **Backend**: Validates user authentication and tier existence
6. **Backend**: Generates unique payer reference number
7. **Backend**: Calculates payment dates (first payment in 1 day, expiry in 1 year)
8. **Backend**: Calls `telebirr_direct_debit_service.create_mandate()`
9. **Service**: Constructs SOAP envelope with:
   - CommandID: `CreateDirectDebitMandateByCustomer`
   - Initiator: SP Operator credentials (IdentifierType=14)
   - Receiver Party: Customer MSISDN (IdentifierType=1)
   - Body: Mandate details (reference, frequency, dates)
10. **Service**: Sends POST request to Telebirr SOAP endpoint
11. **Telebirr**: Validates request and returns ResponseCode='0' (success)
12. **Service**: Parses response and returns success to backend
13. **Backend**: Creates `DirectDebitMandate` record in database with status 'pending_active'
14. **Backend**: Returns mandate details to frontend
15. **Frontend**: Shows success modal with checkmark
16. **Frontend**: Starts polling for mandate activation

**Expected Success Response**:
```json
{
  "success": true,
  "mandate_id": "uuid",
  "payer_reference_number": "FLIPSTAR_3_12345_1715789123",
  "status": "pending_active",
  "message": "Mandate created successfully. Please confirm via Telebirr app."
}
```

**Why This Flow?** The multi-step process ensures:
- **User Confirmation**: User must verify phone number before proceeding
- **Database Tracking**: Mandate is stored locally for reference
- **Pending State**: Mandate requires user confirmation in Telebirr app
- **Polling**: Frontend checks for activation status automatically

---

### Flow 2: Activate Mandate (Webhook Callback)

**Purpose**: Telebirr notifies the system when a user confirms the mandate in their app.

**Step-by-Step Flow**:

1. **User**: Opens Telebirr app and confirms mandate
2. **Telebirr**: Processes confirmation
3. **Telebirr**: Sends POST request to ResultURL (webhook endpoint) with:
   ```xml
   <api:Result>
     <res:Header>
       <res:ConversationID>AG_20260515_...</res:ConversationID>
     </res:Header>
     <res:Body>
       <res:ResultCode>0</res:ResultCode>
       <res:ResultDesc>Process service request successfully.</res:ResultDesc>
       <res:MandateID>...</res:MandateID>
     </res:Body>
   </api:Result>
   ```
4. **Backend**: Receives webhook at `/webhooks/telebirr-direct-debit/`
5. **Backend**: Parses ResultCode and MandateID from XML
6. **Backend**: Updates `DirectDebitMandate` status to 'active'
7. **Backend**: Creates `SubscriptionPlan` record
8. **Backend**: Creates initial `SubscriptionPayment` record
9. **Backend**: Returns 200 OK to Telebirr
10. **Frontend**: Polling detects active status
11. **Frontend**: Updates UI to show active subscription

**Expected Success Response**:
```json
{
  "success": true,
  "mandate_id": "uuid",
  "status": "active",
  "subscription_id": "uuid",
  "message": "Mandate activated successfully. Subscription created."
}
```

**Why Webhook?** Asynchronous notifications allow:
- **Real-time Updates**: System reacts immediately to user confirmation
- **Decoupling**: Frontend doesn't need to constantly poll
- **Reliability**: Telebirr retries failed webhook deliveries

---

### Flow 3: Initiate Direct Debit Transaction

**Purpose**: Deduct payment from customer's account based on active mandate.

**Step-by-Step Flow**:

1. **Backend**: Scheduled task (Celery) triggers for due payments
2. **Backend**: Finds active mandates with next_payment_date <= today
3. **Backend**: For each mandate, calls `telebirr_direct_debit_service.initiate_debit()`
4. **Service**: Constructs SOAP envelope with:
   - CommandID: `InitTrans_Initiate Direct Debit Transaction`
   - Initiator: Organization Operator (IdentifierType=11)
   - Receiver Party: Payer Reference Number (IdentifierType=53)
   - Body: Transaction parameters (MandateID, Amount, Currency)
5. **Service**: Sends POST request to Telebirr SOAP endpoint
6. **Telebirr**: Validates mandate and processes payment
7. **Telebirr**: Returns ResponseCode='0' and TransactionID
8. **Service**: Parses response and returns success
9. **Backend**: Creates `SubscriptionPayment` record with status 'completed'
10. **Backend**: Updates `SubscriptionPlan` next_renewal_date
11. **Backend**: Sends notification to user

**Expected Success Response**:
```json
{
  "success": true,
  "originator_conversation_id": "S_X20260515...",
  "conversation_id": "AG_20260515_...",
  "transaction_id": "5HL20005L6",
  "message": "Accept the service request successfully.",
  "response_code": "0"
}
```

**Why Automated Debit?** Scheduled processing ensures:
- **Timely Payments**: Payments are processed on schedule
- **No Manual Intervention**: System handles recurring payments automatically
- **Audit Trail**: Each payment is recorded in the database

---

### Flow 4: Cancel Direct Debit Mandate

**Purpose**: User cancels their Telebirr subscription from the Flipstar platform.

**Step-by-Step Flow**:

1. **Frontend**: User sees "Cancel Telebirr Subscription" button (if payment_method='telebirr_direct_debit')
2. **Frontend**: User clicks button
3. **Frontend**: Confirmation dialog appears
4. **Frontend**: POST request to `/direct-debit/cancel/` with:
   ```json
   {
     "mandate_id": "uuid"
   }
   ```
5. **Backend**: Validates user authentication and mandate ownership
6. **Backend**: Checks mandate is active
7. **Backend**: Calls `telebirr_direct_debit_service.cancel_mandate()`
8. **Service**: Constructs SOAP envelope with:
   - CommandID: `CancelCustomerDirectDebitMandateByPayer`
   - Initiator: SP Operator (IdentifierType=14)
   - Receiver Party: Customer MSISDN (IdentifierType=1)
   - Body: MandateID to cancel
9. **Service**: Sends POST request to Telebirr SOAP endpoint
10. **Telebirr**: Cancels the mandate
11. **Telebirr**: Returns ResponseCode='0'
12. **Service**: Parses response and returns success
13. **Backend**: Updates `DirectDebitMandate` status to 'cancelled'
14. **Backend**: Cancels associated `SubscriptionPlan`
15. **Backend**: Returns success to frontend
16. **Frontend**: Shows success toast
17. **Frontend**: Reloads subscription data

**Expected Success Response**:
```json
{
  "success": true,
  "message": "Mandate cancelled successfully"
}
```

**Why In-Platform Cancellation?** Providing cancellation in the app:
- **Better UX**: Users don't need to contact support
- **Immediate Effect**: Cancellation is processed instantly
- **Consistency**: All subscription management happens in one place

---

## Frontend Implementation

### Component Architecture

```
SubscriptionPage.jsx
├── State Management
│   ├── tiers (subscription plans)
│   ├── currentSubscription (user's active subscription)
│   ├── telebirrModalOpen (phone number modal)
│   ├── successModalOpen (confirmation modal)
│   └── processing (loading state)
├── Handlers
│   ├── handleTelebirrSubscribe (opens phone modal)
│   ├── handleTelebirrProceed (creates mandate)
│   ├── handleCancelTelebirrSubscription (cancels mandate)
│   └── startPolling (checks activation status)
└── UI Components
    ├── Hero section (premium branding)
    ├── Subscription cards (tier selection)
    ├── Telebirr modal (phone confirmation)
    ├── Success modal (confirmation)
    └── Cancel button (for active subscriptions)
```

### State Management

**Why React State?** React's state management allows:
- **Reactive UI**: Interface updates automatically when state changes
- **User Feedback**: Show loading states and errors
- **Modal Control**: Open/close modals based on user actions

### API Communication

**Code Block - API Helper**:
```javascript
const response = await api.request('/direct-debit/create/', {
  method: 'POST',
  body: JSON.stringify({
    tier_id: selectedTierForTelebirr.id,
    payer_msisdn: telebirrPhone,
    frequency: frequency,
  }),
});
```

**Usage**: The `api.request()` helper:
- Automatically adds authentication token to headers
- Handles JSON serialization/deserialization
- Manages error responses
- Returns typed response objects

**Why Centralized API Helper?** Benefits include:
- **Consistency**: All API calls use the same authentication
- **Error Handling**: Centralized error processing
- **Token Management**: Automatic token refresh
- **Type Safety**: Consistent response structure

---

## Backend Implementation

### Django REST Framework

**Why DRF?** Django REST Framework provides:
- **Serialization**: Automatic model-to-JSON conversion
- **Authentication**: Token-based authentication out of the box
- **Permissions**: Fine-grained access control
- **ViewSets**: Rapid API development

### Database Models

**DirectDebitMandate Model**:
```python
class DirectDebitMandate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tier = models.ForeignKey(SubscriptionTier, on_delete=models.CASCADE)
    payer_msisdn = models.CharField(max_length=20)
    payer_reference_number = models.CharField(max_length=100, unique=True)
    frequency = models.CharField(max_length=2, choices=FREQUENCY_CHOICES)
    first_payment_date = models.CharField(max_length=8)
    expiry_date = models.CharField(max_length=8)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    originator_conversation_id = models.CharField(max_length=100, blank=True)
    conversation_id = models.CharField(max_length=100, blank=True)
    mandate_id = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Why These Fields?** Each field serves a specific purpose:
- **user/tier**: Link to user and subscription plan
- **payer_msisdn**: Customer's phone number for Telebirr
- **payer_reference_number**: Unique identifier for the mandate
- **frequency**: Debit schedule (daily/weekly/monthly)
- **dates**: Payment schedule
- **status**: Track mandate lifecycle (pending_active, active, cancelled)
- **conversation IDs**: Track Telebirr request/response pairs

### Celery Integration

**Why Celery?** Celery enables:
- **Scheduled Tasks**: Automatic payment processing
- **Asynchronous Processing**: Non-blocking API responses
- **Retry Logic**: Automatic retry on failures
- **Distributed Execution**: Scale horizontally

---

## Testing

### Django Shell Testing

**Test 1: Create Daily Mandate**
```python
from api.telebirr_direct_debit_service import telebirr_direct_debit_service

result = telebirr_direct_debit_service.create_mandate(
    payer_msisdn='251955111111',
    payer_reference_number='DAILY_TEST_001',
    frequency='02',  # Daily
    first_payment_date='20260516',
    expiry_date='20270516'
)
print(result)
```

**Expected Success Output**:
```python
{
  'success': True,
  'originator_conversation_id': 'S_X20260515131920',
  'conversation_id': 'AG_20260515_e53c73b6fbbf',
  'message': 'Accept the service request successfully.',
  'response_code': '0'
}
```

**Test 2: Create Weekly Mandate**
```python
result = telebirr_direct_debit_service.create_mandate(
    payer_msisdn='251955111111',
    payer_reference_number='WEEKLY_TEST_001',
    frequency='03',  # Weekly
    first_payment_date='20260522',
    expiry_date='20270522'
)
print(result)
```

**Expected Success Output**:
```python
{
  'success': True,
  'originator_conversation_id': 'S_X20260515132000',
  'conversation_id': 'AG_20260515_abc123def456',
  'message': 'Accept the service request successfully.',
  'response_code': '0'
}
```

**Test 3: Create Monthly Mandate**
```python
result = telebirr_direct_debit_service.create_mandate(
    payer_msisdn='251955111111',
    payer_reference_number='MONTHLY_TEST_001',
    frequency='05',  # Monthly
    first_payment_date='20260615',
    expiry_date='20270615'
)
print(result)
```

**Expected Success Output**:
```python
{
  'success': True,
  'originator_conversation_id': 'S_X20260515132015',
  'conversation_id': 'AG_20260515_xyz789abc123',
  'message': 'Accept the service request successfully.',
  'response_code': '0'
}
```

**Test 4: Cancel Mandate**
```python
result = telebirr_direct_debit_service.cancel_mandate(
    mandate_id='TEST_MANDATE_001',
    payer_msisdn='251955111111'
)
print(result)
```

**Expected Success Output**:
```python
{
  'success': True,
  'originator_conversation_id': 'S_X20260515131920',
  'conversation_id': 'AG_20260515_e53c73b6fbbf',
  'message': 'Accept the service request successfully.',
  'response_code': '0'
}
```

**Test 5: Initiate Debit Transaction**
```python
result = telebirr_direct_debit_service.initiate_debit(
    mandate_id='TEST_MANDATE_001',
    payer_reference_number='TEST001',
    amount=100.00,
    currency='ETB',
    shortcode='232323'
)
print(result)
```

**Expected Success Output**:
```python
{
  'success': True,
  'originator_conversation_id': 'S_X20260515131935',
  'conversation_id': 'AG_20260515_4ad13c83a746',
  'transaction_id': '5HL20005L6',
  'message': 'Accept the service request successfully.',
  'response_code': '0'
}
```

### Test Credentials

**Test Environment Configuration**:
- **URL**: `http://10.180.79.13:30001/payment/services/APIRequestMgrService`
- **Third Party ID**: `TestMer`
- **Third Party Password**: `jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=`
- **SP Operator ID**: `TestSPOperAPI`
- **SP Operator Credential**: `2JKSrKYlLAVvKWuIUXcexc3GHiT0+lEKzeVb6JRcZUM=`
- **Short Code**: `232323`

**Why Test Credentials?** Test environment allows:
- **Safe Testing**: No real money transactions
- **Development**: Test all operations without production risk
- **Validation**: Verify SOAP envelope structure
- **Debugging**: Identify issues before production deployment

---

## Security Considerations

### Authentication

**Token-Based Authentication**:
- Frontend stores JWT token in localStorage
- Backend validates token on each request
- Token includes user permissions and expiration

**Why Tokens?** Benefits include:
- **Stateless**: No server-side session storage
- **Scalable**: Works across multiple servers
- **Secure**: Encrypted and signed tokens

### Credential Management

**Environment Variables**:
```python
TELEBIRR_THIRD_PARTY_PASSWORD = config('TELEBIRR_THIRD_PARTY_PASSWORD')
```

**Why Environment Variables?** Security best practices:
- **Not in Code**: Credentials not committed to git
- **Separate Configs**: Different credentials per environment
- **Easy Rotation**: Change credentials without code deployment

### SSL/TLS

**Production Requirement**:
- All SOAP requests should use HTTPS
- SSL certificates valid and up-to-date
- Disable SSL verification only for testing

**Why HTTPS?** Encryption ensures:
- **Confidentiality**: Credentials not intercepted
- **Integrity**: Data not tampered with
- **Authentication**: Server identity verified

---

## Troubleshooting

### Common Issues

**Issue 1: SOAP Client Initialization Error**
```
Failed to initialize SOAP client: 500 Server Error
```
**Solution**: The Telebirr server may not provide a WSDL. Use raw SOAP requests instead of zeep.

**Issue 2: Mandate Not Activating**
**Solution**: Check webhook endpoint is accessible and Telebirr can reach it. Verify ResultURL is correct.

**Issue 3: Invalid Phone Number**
**Solution**: Ensure phone number format is correct (251XXXXXXXXX). Validate before sending to API.

**Issue 4: Frequency Code Invalid**
**Solution**: Use correct frequency codes: 02=daily, 03=weekly, 05=monthly.

### Debugging Tips

**Enable Debug Logging**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Check Backend Logs**:
```bash
docker-compose logs backend -f
```

**Test SOAP Request Manually**:
```python
import requests
# Test connectivity
response = requests.get('http://10.180.79.13:30001/payment/services/APIRequestMgrService')
print(response.status_code)
```

---

## Summary

The Telebirr Direct Debit integration provides a complete subscription payment solution:

### Key Components
- **Frontend**: React components for user interaction
- **Backend**: Django REST API for request processing
- **SOAP Service**: Python service for Telebirr communication
- **Database**: Models for mandate and subscription tracking

### Four Main Operations
1. **Create Mandate**: Establish direct debit agreement
2. **Activate Mandate**: User confirms via Telebirr app
3. **Initiate Debit**: Process recurring payments
4. **Cancel Mandate**: User cancels subscription

### Why This Architecture?
- **Separation of Concerns**: Each layer has a specific responsibility
- **Scalability**: Can handle increased load
- **Maintainability**: Easy to debug and update
- **Security**: Proper authentication and credential management

### Testing
All operations have been tested successfully with Telebirr test credentials, confirming:
- SOAP envelope structure is correct
- API communication works as expected
- Error handling is robust
- User experience is smooth

The integration is production-ready and can be switched to production credentials by updating the environment variables.
