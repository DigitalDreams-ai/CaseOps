@isTest
public with sharing class Patient_TestSuite {

    @TestSetup
    static void makeData(){
        // Create New Person Account
        Account account = new Account();
        account.FirstName = 'Test';
        account.LastName = 'Patient';
        account.BillingCity = 'New York';
        account.BillingState = 'NY';
        account.BillingPostalCode = '10001';
        account.BillingCountry = 'USA';
        account.BillingStreet = '123 Main St';        
        account.PersonEmail = 'test@10xhealthsystem.com';
        account.PersonMobilePhone = '1234567890';
        account.RecordTypeId = Schema.SObjectType.Account.getRecordTypeInfosByName().get('Patient Account Record Type').getRecordTypeId();
        insert account;

        // New Patient Agreement Configuration
        Patient_Agreement_Configuration__c agreementConfig = new Patient_Agreement_Configuration__c();
        agreementConfig.Name = 'Test Agreement Config';
        agreementConfig.Agreement_Id__c = 'bz0-000000000000000';
        agreementConfig.Recurrence_Schedule__c = 'Once';
        agreementConfig.Agreement_Source__c = 'Biocanic';
        insert agreementConfig;

        // New Patient Agreement
        Patient_Agreement__c agreement = new Patient_Agreement__c();
        agreement.Name = 'Test Agreement';
        agreement.Patient__c = account.Id;
        agreement.Patient_Agreement_Configuration__c = agreementConfig.Id;
        agreement.Date_Sent__c = Date.today();
        insert agreement;
    }

    public static void createPatientWithBirthMonth(String birthMonth, String gender) {
        // Create test data
        Patient_DS_Event patientEvent = new Patient_DS_Event();
        patientEvent.eventId = 'aZ000B000000000AAA';
        patientEvent.eventType = 'CreatePatient';

        Patient_DS_Patient patientData = new Patient_DS_Patient();
        patientData.firstName = 'Test';
        patientData.lastName = 'Patient';
        patientData.email = 'test@10xhealth.com';
        patientData.phone = '1234567890';
        patientData.birthdate = birthMonth + ' 8, 2023'; // Change the birth month here
        patientData.gender = gender;
        patientData.mobile = '1234567890';

        patientData.billingAddress = new Patient_DS_Address();
        patientData.billingAddress.city = 'New York';
        patientData.billingAddress.state = 'NY';
        patientData.billingAddress.zip = '10001';
        patientData.billingAddress.country = 'USA';
        patientData.billingAddress.street = '123 Main St';

        patientData.shippingAddress = new Patient_DS_Address();
        patientData.shippingAddress.city = 'New York';
        patientData.shippingAddress.state = 'NY';
        patientData.shippingAddress.zip = '10001';
        patientData.shippingAddress.country = 'USA';
        patientData.shippingAddress.street = '123 Main St';

        Patient_Patient.Request request = new Patient_Patient.Request();
        request.event = patientEvent;
        request.patient = patientData;

        List<Patient_Patient.Request> requests = new List<Patient_Patient.Request>();
        requests.add(request);

        HttpCalloutMockFactory mock = new HttpCalloutMockFactory(201, 'OK', 'OK', new Map<String, String>());
		test.setMock(HttpCalloutMock.class, mock);
		test.startTest();
		Patient_patient.Submit_Patient(requests);
		test.stopTest();
		// Assert logs were generated. Note, MakeAPIcall logs once.
		List<DrChrono_Request_Log__c> logs = [SELECT Id FROM DrChrono_Request_Log__c];
		// Assert.areEqual(3, logs.size());
    }

    @isTest
    public static void createPatientSuccess_January() {
        createPatientWithBirthMonth('January','Male');
    }

    @isTest
    public static void createPatientSuccess_February() {
        createPatientWithBirthMonth('February','male');
    }

    @isTest
    public static void createPatientSuccess_March() {
        createPatientWithBirthMonth('March','male');
    }

    @isTest
    public static void createPatientSuccess_April() {
        createPatientWithBirthMonth('April','female');
    }

    @isTest
    public static void createPatientSuccess_May() {
        createPatientWithBirthMonth('May','Female');
    }

    @isTest
    public static void createPatientSuccess_June() {
        createPatientWithBirthMonth('June','Male');
    }

    @isTest
    public static void createPatientSuccess_July() {
        createPatientWithBirthMonth('July','Male');
    }

    @isTest
    public static void createPatientSuccess_August() {
        createPatientWithBirthMonth('August','Male');
    }

    @isTest
    public static void createPatientSuccess_September() {
        createPatientWithBirthMonth('September','Male');
    }

    @isTest
    public static void createPatientSuccess_October() {
        createPatientWithBirthMonth('October','Female');
    }

    @isTest
    public static void createPatientSuccess_November() {
        createPatientWithBirthMonth('November','Female');
    }

    @isTest
    public static void createPatientSuccess_December() {
        createPatientWithBirthMonth('December','FeMale');
    }

    // Test Classes for Submitting Forms
    @isTest
    public static void sendConsentForms() {
        // Select the Patient Agreement and Patient Agreement Configuration
        Patient_Agreement__c agreement = [SELECT Id, Name, Patient__c, Patient_Agreement_Configuration__c FROM Patient_Agreement__c LIMIT 1];
        Patient_Agreement_Configuration__c agreementConfig = [SELECT Id, Name, Agreement_Id__c FROM Patient_Agreement_Configuration__c WHERE Id = :agreement.Patient_Agreement_Configuration__c LIMIT 1];

        Test.startTest();
        // Create test data
        List<Patient_DS_ConsentForm_RequestForms> consentForms = new List<Patient_DS_ConsentForm_RequestForms>();
        Patient_DS_ConsentForm_RequestForms consentForm = new Patient_DS_ConsentForm_RequestForms();
        consentForm.formId = agreementConfig.Agreement_Id__c;
        consentForm.salesforceAgreementId = agreement.Id;
        consentForms.add(consentForm);

        List<Patient_DS_ConsentForm_Request> consentRequests = new List<Patient_DS_ConsentForm_Request>();
        Patient_DS_ConsentForm_Request consentRequest = new Patient_DS_ConsentForm_Request();
        consentRequest.accountId = agreement.Patient__c;
        consentRequest.forms = consentForms;
        consentRequests.add(consentRequest);

        List<Patient_SendConsentForm.Request> requestWrappers = new List<Patient_SendConsentForm.Request>();
        Patient_SendConsentForm.Request requestWrapper = new Patient_SendConsentForm.Request();
        requestWrapper.request = consentRequests;
        requestWrappers.add(requestWrapper);

        HttpCalloutMockFactory mock = new HttpCalloutMockFactory(200, 'OK', '{"success":true, "errorMessage":"", "items":[{"salesforceAgreementId":"' + getPatientAgreementKeyPrefix() + '000000000000000", "formId": "asdf", "biocanicAssignementId": "123", "success":true, "errorMessage":""}]} ', new Map<String, String>());
		test.setMock(HttpCalloutMock.class, mock);
		Patient_SendConsentForm.Patient_SendConsentForm(requestWrappers);
		test.stopTest();
		List<DrChrono_Request_Log__c> logs = [SELECT Id FROM DrChrono_Request_Log__c];
		// Assert.isTrue(logs.size() >= 4);
    }

    //Helper methods
	private static String getPatientAgreementKeyPrefix(){
		SObject agreementObj = (SObject) Patient_Agreement__c.class.newInstance();
		return agreementObj.getSObjectType().getDescribe().getKeyPrefix();
	}
}