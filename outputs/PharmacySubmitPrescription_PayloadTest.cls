/**
 * Test class to verify Wellvi eSubmit payload includes address fields at correct JSON paths.
 * Verifies CMT JSON path fix for HEAL-33633: address fields should be at root level (City, PostalCode, AddressLine1, StateProvince)
 * not nested under shippingAddress.
 */
@IsTest
public with sharing class PharmacySubmitPrescription_PayloadTest {

    // Static holder for captured payload
    private static String capturedRequestBody;

    @TestSetup
    static void setupTestData() {
        // Create Patient Account with minimal required fields
        RecordType patientRT = [SELECT Id FROM RecordType
                               WHERE SObjectType = 'Account'
                               AND DeveloperName = 'Patient_Account_Record_Type'
                               LIMIT 1];

        Account patientAccount = new Account(
            FirstName = 'Joshua',
            LastName = 'Brown',
            RecordTypeId = patientRT.Id,
            UUID__c = 'PT-TEST-001',
            Gender__c = 'Male',
            DateOfBirth__c = Date.newInstance(1990, 1, 1)
        );
        insert patientAccount;

        // Get standard pricebook
        Id stdPricebookId = Test.getStandardPricebookId();

        // Create Product
        Product2 testProduct = new Product2(
            Name = 'Test Prescription Product',
            IsActive = true
        );
        insert testProduct;

        // Create PricebookEntry
        PricebookEntry pbe = new PricebookEntry(
            Pricebook2Id = stdPricebookId,
            Product2Id = testProduct.Id,
            UnitPrice = 50.00,
            IsActive = true,
            NDC__c = 'TEST123456789'
        );
        insert pbe;

        // Create Order with custom shipping address fields
        Order testOrder = new Order(
            AccountId = patientAccount.Id,
            Pricebook2Id = stdPricebookId,
            EffectiveDate = Date.today(),
            Status = 'Draft',
            UUID__c = 'ORD-TEST-001',
            Shipping_Street__c = '123 Test Street',
            Shipping_City__c = 'Test City',
            Shipping_State__c = 'CA',
            Shipping_Zip_Code__c = '90210'
        );
        insert testOrder;
    }

    /**
     * Test Case: Verify address fields appear at root level with correct PascalCase (fixed CMT paths)
     * This test directly constructs the payload using PharmacySubmitPrescriptionCallout to verify
     * the CMT JSON paths correctly map address fields to root-level properties.
     */
    @IsTest
    static void testWellviPayload_AddressFieldsAtRootLevel() {
        Test.setMock(HttpCalloutMock.class, new WellviPayloadCaptureMock());

        Account testAccount = [SELECT Id FROM Account WHERE FirstName = 'Joshua' AND LastName = 'Brown'];
        Order testOrder = [SELECT Id FROM Order WHERE AccountId = :testAccount.Id];

        Test.startTest();
        try {
            // Create the callout object which builds the payload from CMT metadata
            PharmacySubmitPrescriptionCallout pspc = new PharmacySubmitPrescriptionCallout('Wellvi_Submit_Prescription', testOrder.Id);
            // This internally calls buildBody() which uses CMT metadata to construct the JSON payload

            // Invoke the callout (will be mocked and captured)
            Integer statusCode = pspc.invoke();
            System.assertEquals(200, statusCode, 'Callout should return mock 200 response');
        } catch(Exception e) {
            System.assert(false, 'Test should not throw exception. Error: ' + e.getMessage() + ' - ' + e.getStackTraceString());
        }
        Test.stopTest();

        // Verify the captured payload structure
        System.assertNotEquals(null, capturedRequestBody, 'Mock should have captured request body');
        System.debug('Captured Wellvi payload: ' + capturedRequestBody);

        // Deserialize and verify address fields
        try {
            Map<String, Object> payloadMap = (Map<String, Object>) JSON.deserializeUntyped(capturedRequestBody);

            // Verify address fields are present at root level with correct values
            // This validates the CMT JSON path fix (mappings should be $.City, $.PostalCode, etc., not nested)
            String city = String.valueOf(payloadMap.get('City'));
            String postalCode = String.valueOf(payloadMap.get('PostalCode'));
            String addressLine1 = String.valueOf(payloadMap.get('AddressLine1'));
            String stateProvince = String.valueOf(payloadMap.get('StateProvince'));

            System.assertEquals('Test City', city,
                'City MUST be at root level and match Order Shipping_City__c = "Test City"');
            System.assertEquals('90210', postalCode,
                'PostalCode MUST be at root level and match Order Shipping_Zip_Code__c = "90210"');
            System.assertEquals('123 Test Street', addressLine1,
                'AddressLine1 MUST be at root level and match Order Shipping_Street__c = "123 Test Street"');
            System.assertEquals('CA', stateProvince,
                'StateProvince MUST be at root level and match Order Shipping_State__c = "CA"');
        } catch(Exception e) {
            System.assert(false, 'Failed to parse or validate payload: ' + e.getMessage());
        }
    }

    /**
     * Mock callout class to capture HTTP request payload
     */
    public class WellviPayloadCaptureMock implements HttpCalloutMock {

        public HttpResponse respond(HttpRequest request) {
            HttpResponse response = new HttpResponse();
            response.setHeader('Content-Type', 'application/json');

            // Capture request body for verification in test
            capturedRequestBody = request.getBody();

            System.debug('PAYLOAD_CAPTURE: ' + request.getBody());
            System.debug('ENDPOINT: ' + request.getEndpoint());
            System.debug('METHOD: ' + request.getMethod());

            // Return mock success response (matches SubmitPrescriptionResponse structure)
            response.setStatusCode(200);
            response.setBody('{"prescriptionResults": []}');

            return response;
        }
    }
}
