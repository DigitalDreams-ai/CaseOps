Savepoint sp = Database.setSavepoint();
Boolean passed = false;
String failureMessage = null;

try {
    String stamp = String.valueOf(DateTime.now().getTime());
    Id patientRtId = [
        SELECT Id
        FROM RecordType
        WHERE SObjectType = 'Account'
        AND DeveloperName = 'Patient_Account_Record_Type'
        LIMIT 1
    ].Id;

    Account patient = new Account(
        RecordTypeId = patientRtId,
        FirstName = 'HEAL33418',
        LastName = 'Flow Test ' + stamp,
        PersonEmail = 'heal33418-flow-test@example.invalid',
        Gender__c = 'Male'
    );
    insert patient;

    Patient_Agreement_Configuration__c informedConsentPac = new Patient_Agreement_Configuration__c(
        Name = 'Informed Consent HEAL33418 ' + stamp,
        Agreement_Id__c = 'IC-' + stamp,
        Recurrence_Schedule__c = 'Once',
        Agreement_Source__c = 'MyWellnessPortal',
        Consent_Type__c = 'Explicit Consent'
    );
    insert informedConsentPac;

    Patient_Agreement_Configuration__c selectedPac = new Patient_Agreement_Configuration__c(
        Name = 'HEAL33418 Selected Agreement ' + stamp,
        Agreement_Id__c = 'SEL-' + stamp,
        Recurrence_Schedule__c = 'Once',
        Agreement_Source__c = 'MyWellnessPortal',
        Consent_Type__c = 'Explicit Consent'
    );
    insert selectedPac;

    Patient_Agreement__c expiredExistingIc = new Patient_Agreement__c(
        Name = 'Informed Consent Existing Expired ' + stamp,
        Patient__c = patient.Id,
        Patient_Agreement_Configuration__c = informedConsentPac.Id,
        Date_Sent__c = DateTime.now().addMonths(-13)
    );
    insert expiredExistingIc;
    expiredExistingIc.put('Expiration_Date__c', Date.today().addDays(-1));
    expiredExistingIc.put('Status__c', 'Sent');
    update expiredExistingIc;

    Map<String, Object> inputs = new Map<String, Object>();
    inputs.put('rec_Account', patient);
    inputs.put('col_PatientAgreementConfigurtion', new List<Patient_Agreement_Configuration__c>{ selectedPac });

    Flow.Interview.Autolaunch_Send_Patient_Agreements_to_Patient interview =
        new Flow.Interview.Autolaunch_Send_Patient_Agreements_to_Patient(inputs);
    interview.start();

    List<Patient_Agreement__c> agreements = [
        SELECT Id, Name, Patient_Agreement_Configuration__c, Date_Sent__c
        FROM Patient_Agreement__c
        WHERE Patient__c = :patient.Id
        ORDER BY CreatedDate ASC
    ];

    Integer selectedCount = 0;
    Integer informedConsentCount = 0;
    for (Patient_Agreement__c agreement : agreements) {
        if (agreement.Patient_Agreement_Configuration__c == selectedPac.Id) {
            selectedCount++;
        }
        if (agreement.Patient_Agreement_Configuration__c == informedConsentPac.Id) {
            informedConsentCount++;
        }
    }

    System.debug('HEAL33418_TEST_ACCOUNT=' + patient.Id);
    System.debug('HEAL33418_SELECTED_COUNT=' + selectedCount);
    System.debug('HEAL33418_INFORMED_CONSENT_COUNT=' + informedConsentCount);
    System.debug('HEAL33418_TOTAL_PATIENT_AGREEMENTS=' + agreements.size());

    passed = selectedCount >= 1 && informedConsentCount >= 2;
    if (!passed) {
        failureMessage = 'Expected the flow to create a selected agreement and a new Informed Consent when an expired Informed Consent already exists. selectedCount='
            + selectedCount + ', informedConsentCount=' + informedConsentCount + ', total=' + agreements.size();
    }
} catch (Exception e) {
    failureMessage = e.getTypeName() + ': ' + e.getMessage() + ' at line ' + e.getLineNumber();
}

Database.rollback(sp);

if (!passed) {
    System.debug('HEAL33418_TEST_RESULT=FAIL');
    System.debug('HEAL33418_TEST_FAILURE=' + failureMessage);
    throw new AuraHandledException(failureMessage);
}

System.debug('HEAL33418_TEST_RESULT=PASS');
