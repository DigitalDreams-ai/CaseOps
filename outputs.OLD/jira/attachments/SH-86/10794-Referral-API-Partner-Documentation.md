# Referral API Documentation

## Overview

The Referral API enables partners to create and update referral records in the Litify case management system. This API uses Salesforce REST endpoints with OAuth 2.0 authentication and API key validation.

**Base URL:** `{base_url}/services/apexrest/v1/referrals`

The `base_url` is obtained from the OAuth token response and should be used as the base for all API requests.

---

## Authentication

All API requests require two forms of authentication:

1. **Salesforce OAuth 2.0 Bearer Token** - Standard Salesforce authentication
2. **API Key** - Provided to your organization for partner identification

### Getting an OAuth Token

Authenticate using Salesforce OAuth 2.0 Client Credentials flow:

**Endpoint:** `POST {base_url}/services/oauth2/token`

Where `{base_url}` should be set to:
- Sandbox: `https://shulman-hill--uat.sandbox.my.salesforce.com`

**Request Headers:**
```
Content-Type: application/x-www-form-urlencoded
```

**Request Body (form-urlencoded):**
```
grant_type=client_credentials
&client_id={client_id}
&client_secret={client_secret}
```

**Response:**
```json
{
  "access_token": "{access_token}",
  "instance_url": "{base_url}",
  "id": "{id}",
  "token_type": "Bearer",
  "issued_at": "{issued_at}",
  "signature": "{signature}"
}
```

### Using the Access Token

Store the `access_token` and `base_url` from the OAuth response. The `base_url` is your base URL for all API requests.

---

## API Endpoints

### 1. Create Referral

Creates a new referral record.

**Endpoint:** `POST /services/apexrest/v1/referrals`

**Request Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
X-API-KEY: {partner_api_key}
```

**Request Body:**
```json
{
  "clientFirstName": "John",
  "clientLastName": "Doe",
  "clientEmail": "john.doe@email.com",
  "clientPhone": "(555) 123-4567",
  "description": "Work-related injury claim from prolonged computer work",
  "status": "new",
  "incidentDate": "2024-01-15",
  "caseType": "Workers Compensation"
}
```

**Response (201 Created):**
```json
{
  "referralId": "{referralId}",
  "message": "Referral created successfully"
}
```

The `referralId` is a Salesforce record ID (15 or 18 characters) that should be stored for future update operations.

**Response (400 Bad Request):**
```json
{
  "errorMessage": "Validation failed: Client email must be a valid email address"
}
```

**Response (401 Unauthorized):**
```json
{
  "errorMessage": "Invalid or missing API key"
}
```

---

### 2. Update Referral

Updates an existing referral record. Only include fields that need to be updated.

**Endpoint:** `PUT /services/apexrest/v1/referrals/{referralId}`

**Path Parameters:**
- `referralId` (required) - The Salesforce ID of the referral to update (15 or 18 characters)

**Request Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
X-API-KEY: {partner_api_key}
```

**Request Body:**
```json
{
  "status": "active",
  "description": "Updated case description with additional details from medical examination"
}
```

**Response (200 OK):**
```json
{
  "referralId": "{referralId}",
  "message": "Referral updated successfully"
}
```

**Response (400 Bad Request):**
```json
{
  "errorMessage": "Referral ID is required in URL path"
}
```

**Response (404 Not Found):**
```json
{
  "errorMessage": "Referral not found"
}
```

---

### 3. Get Referral by ID

Retrieves a specific referral record by its Salesforce ID.

**Endpoint:** `GET /services/apexrest/v1/referrals/{referralId}`

**Path Parameters:**
- `referralId` (required) - The Salesforce ID of the referral to retrieve (15 or 18 characters)

**Request Headers:**
```
Authorization: Bearer {access_token}
X-API-KEY: {partner_api_key}
```

**Response (200 OK):**
```json
{
  "referralId": "{referralId}",
  "clientFirstName": "John",
  "clientLastName": "Doe",
  "clientEmail": "john.doe@email.com",
  "clientPhone": "(555) 123-4567",
  "description": "Work-related injury claim from prolonged computer work",
  "status": "new",
  "incidentDate": "2024-01-15",
  "caseType": "Workers Compensation"
}
```

**Response (404 Not Found):**
```json
{
  "errorMessage": "Referral not found"
}
```

**Response (401 Unauthorized):**
```json
{
  "errorMessage": "Invalid or missing API key"
}
```

---

### 4. Get All Referrals

Retrieves all referral records for your firm (automatically filtered by your API key).

**Endpoint:** `GET /services/apexrest/v1/referrals`

**Request Headers:**
```
Authorization: Bearer {access_token}
X-API-KEY: {partner_api_key}
```

**Response (200 OK):**
```json
{
  "referrals": [
    {
      "referralId": "{referralId1}",
      "clientFirstName": "John",
      "clientLastName": "Doe",
      "clientEmail": "john.doe@email.com",
      "clientPhone": "(555) 123-4567",
      "description": "Work-related injury claim",
      "status": "new",
      "incidentDate": "2024-01-15",
      "caseType": "Workers Compensation"
    },
    {
      "referralId": "{referralId2}",
      "clientFirstName": "Jane",
      "clientLastName": "Smith",
      "clientEmail": "jane.smith@email.com",
      "clientPhone": "(555) 987-6543",
      "description": "Motor vehicle accident case",
      "status": "active",
      "incidentDate": "2024-02-20",
      "caseType": "PI - MVA"
    }
  ],
  "count": 2
}
```

**Response (401 Unauthorized):**
```json
{
  "errorMessage": "Invalid or missing API key"
}
```

---

## Request Fields

The following fields are available for use in API requests:

| Field Name | Type | Required | Description | Validation Rules |
|------------|------|----------|-------------|------------------|
| `clientFirstName` | String | Yes* | Client's first name | Maximum 255 characters |
| `clientLastName` | String | Yes* | Client's last name | Maximum 255 characters |
| `clientEmail` | String | Yes* | Client's email address | Valid email format |
| `clientPhone` | String | Optional | Client's phone number | Accepts various formats: (555) 123-4567, 555-123-4567, 5551234567 |
| `description` | String | Optional | Description of the case | Maximum 131,072 characters |
| `status` | String | Optional | Current status of the referral | See Status Values below |
| `incidentDate` | Date | Optional | Date of the incident | Format: YYYY-MM-DD. Cannot be in the future |
| `caseType` | String | Yes* | Type of legal case | See Case Type Values below |

\* Required for creating a new referral

---

## Status Values

The `status` field accepts the following values:

- `new` - New referral
- `active` - Active referral
- `cancelled` - Cancelled referral
- `draft` - Draft referral
- `pending` - Pending referral

**Note:** Status values are case-sensitive. Use lowercase values as shown above.

---

## Case Type Values

The `caseType` field accepts the following values:

- `Workers Compensation`
- `PI - MVA`
- `PI - Premises`
- `PI - Labor Law`
- `SSD`
- `Civil Rights`
- `Other`

**Important:**
Case type values must match exactly as shown above (including spaces, hyphens, and capitalization).
Case Types that do not match will default to 'Other'.

---

## Field Validation Rules

### Email Validation
- Must be a valid email address format

### Phone Number Validation
- Accepts various formats including `(555) 123-4567`, `555-123-4567`, or `5551234567`
- Phone numbers are automatically formatted to `(XXX) XXX-XXXX` format
- Maximum 20 characters

### Date Validation
- Format: `YYYY-MM-DD` (ISO 8601 date format)
- `incidentDate` cannot be in the future

### String Length Validation
- Names (`clientFirstName`, `clientLastName`): Maximum 255 characters
- `description`: Maximum 131,072 characters

---

## Error Responses

### 400 Bad Request
Returned when:
- Invalid JSON format
- Missing required fields
- Invalid field values
- Validation errors

**Example:**
```json
{
  "errorMessage": "Validation failed: Client email must be a valid email address"
}
```

### 401 Unauthorized
Returned when:
- Invalid or missing API key
- Invalid or expired OAuth token

**Example:**
```json
{
  "errorMessage": "Invalid or missing API key"
}
```

### 404 Not Found
Returned when:
- Referral ID not found
- Referral does not belong to the authenticated firm

**Example:**
```json
{
  "errorMessage": "Referral not found"
}
```

### 500 Internal Server Error
Returned when:
- Server-side errors occur
- Database errors

**Example:**
```json
{
  "errorMessage": "Internal server error occurred"
}
```

---

## Usage Examples

### cURL Examples

#### Create a New Referral

```bash
curl -X POST "{base_url}/services/apexrest/v1/referrals" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: {partner_api_key}" \
  -d '{
    "clientFirstName": "John",
    "clientLastName": "Doe",
    "clientEmail": "john.doe@email.com",
    "clientPhone": "(555) 123-4567",
    "description": "Work-related injury claim",
    "status": "new",
    "incidentDate": "2024-01-15",
    "caseType": "Workers Compensation"
  }'
```

#### Update a Referral Status

```bash
curl -X PUT "{base_url}/services/apexrest/v1/referrals/{referralId}" \
  -H "Authorization: Bearer {access_token}" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: {partner_api_key}" \
  -d '{
    "status": "active"
  }'
```

#### Get a Referral by ID

```bash
curl -X GET "{base_url}/services/apexrest/v1/referrals/{referralId}" \
  -H "Authorization: Bearer {access_token}" \
  -H "X-API-KEY: {partner_api_key}"
```

#### Get All Referrals

```bash
curl -X GET "{base_url}/services/apexrest/v1/referrals" \
  -H "Authorization: Bearer {access_token}" \
  -H "X-API-KEY: {partner_api_key}"
```

---

### JavaScript Example

```javascript
// Create a new referral
async function createReferral() {
  const baseUrl = '{base_url}'; // From OAuth response
  const accessToken = '{access_token}'; // From OAuth response
  const partnerApiKey = '{partner_api_key}'; // Provided separately

  const response = await fetch(`${baseUrl}/services/apexrest/v1/referrals`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
      'X-API-KEY': partnerApiKey
    },
    body: JSON.stringify({
      clientFirstName: 'John',
      clientLastName: 'Doe',
      clientEmail: 'john.doe@email.com',
      clientPhone: '(555) 123-4567',
      description: 'Work-related injury claim',
      status: 'new',
      incidentDate: '2024-01-15',
      caseType: 'Workers Compensation'
    })
  });

  const data = await response.json();
  console.log('Referral created:', data.referralId);
}
```

---

### Python Example

```python
import requests

# Create a new referral
def create_referral():
    base_url = "{base_url}"  # From OAuth response
    access_token = "{access_token}"  # From OAuth response
    partner_api_key = "{partner_api_key}"  # Provided separately

    url = f"{base_url}/services/apexrest/v1/referrals"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-API-KEY": partner_api_key
    }
    data = {
        "clientFirstName": "John",
        "clientLastName": "Doe",
        "clientEmail": "john.doe@email.com",
        "clientPhone": "(555) 123-4567",
        "description": "Work-related injury claim",
        "status": "new",
        "incidentDate": "2024-01-15",
        "caseType": "Workers Compensation"
    }

    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    print(f"Referral created: {result['referralId']}")
```

---

## Postman Collection

A Postman collection is available for testing the API. The collection is named **"Referral API Collection"** (version 1.0.0) and includes:

- **Create Referral** - POST request to create new referrals
- **Update Referral** - PUT request to update existing referrals
- **Get Referral by ID** - GET request to retrieve a specific referral by its ID
- **Get Referrals** - GET request to retrieve all referrals for your firm
- **Get Salesforce OAuth Token** - POST request to authenticate and obtain access token
- **Examples** - Example requests for Workers Compensation and Medical Malpractice cases
- **Validation Error Example** - Example request demonstrating validation errors

### Importing the Collection

1. Import `ReferralAPI-Postman-Collection.json` into Postman
2. Import `ReferralAPI-Environment.postman_environment.json` as a Postman environment
3. Select the **"Referral API Environment"** environment in Postman

### Postman Environment Variables

Configure these variables in the **"Referral API Environment"**:

**From Environment File:**
- `base_url` - Salesforce instance URL (set to the sandbox/production login URL, e.g., `https://shulman-hill--uat.sandbox.my.salesforce.com`)
- `grant_type` - Set to `client_credentials` (already configured in environment file)
- `client_id` - Connected App Consumer Key (provided separately)
- `client_secret` - Connected App Consumer Secret (provided separately)
- `partner_api_key` - Your partner API key (provided separately)

**Automatically Set Variables** (set by collection requests):
- `access_token` - OAuth access token (set by "Get Salesforce OAuth Token" request)
- `base_url` - Salesforce instance URL (set by "Get Salesforce OAuth Token" request)
- `referral_id` - Referral ID (set by "Create Referral" request)

### Using the Collection

1. **Initial Setup:** Configure the environment variables:
   - Set `base_url` to your Salesforce login URL (e.g., `https://shulman-hill--uat.sandbox.my.salesforce.com`)
   - Set `client_id` and `client_secret` with your Connected App credentials
   - Set `partner_api_key` with your assigned API key

2. Run the **"Get Salesforce OAuth Token"** request to authenticate. This will:
   - Set the `access_token` variable
   - Update the `base_url` variable with your Salesforce instance URL (returned from OAuth response)

3. Use the **"Create Referral"** request to create new referrals. The `referral_id` will be automatically saved for use in the **"Update Referral"** and **"Get Referral by Id"** requests

---

## Best Practices

1. **Always include required fields** when creating a new referral
2. **Store the referralId** from the create response for future updates
3. **Handle errors gracefully** - check response status codes and error messages
4. **Validate data client-side** before sending requests to improve error handling
5. **Use appropriate HTTP methods** - POST for create, PUT for update
6. **Include only changed fields** in update requests
7. **Retry logic** - Implement retry logic for 500 errors, but not for 400/401 errors
8. **Token refresh** - Implement token refresh logic for expired access tokens

---

## Collection Details

- **Collection Name:** Referral API Collection
- **Collection Description:** Salesforce Referral API for creating and updating litify_pm__Referral__c records
- **Collection Version:** 1.0.0
- **Environment Name:** Referral API Environment
- **Environment ID:** referral-api-env