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
        LastName = 'Smoke Test ' + stamp,
        PersonEmail = 'heal33418-smoke-test@example.invalid',
        Gender__c = 'Male'
    );
    insert patient;

    Patient_Agreement_Configuration__c informedConsentPac = new Patient_Agreement_Configuration__c(
        Name = 'Informed Consent HEAL33418 ' + stamp,
        Agreement_Id__c = 'ICSMOKE-' + stamp,
        Recurrence_Schedule__c = 'Once',
        Agreement_Source__c = 'MyWellnessPortal',
        Consent_Type__c = 'Explicit Consent'
    );
    insert informedConsentPac;

    Patient_Agreement_Configuration__c selectedPac = new Patient_Agreement_Configuration__c(
        Name = 'HEAL33418 Selected Agreement ' + stamp,
        Agreement_Id__c = 'SELSMOKE-' + stamp,
        Recurrence_Schedule__c = 'Once',
        Agreement_Source__c = 'MyWellnessPortal',
        Consent_Type__c = 'Explicit Consent'
    );
    insert selectedPac;

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

    System.debug('HEAL33418_SMOKE_ACCOUNT=' + patient.Id);
    System.debug('HEAL33418_SMOKE_SELECTED_COUNT=' + selectedCount);
    System.debug('HEAL33418_SMOKE_INFORMED_CONSENT_COUNT=' + informedConsentCount);
    System.debug('HEAL33418_SMOKE_TOTAL_PATIENT_AGREEMENTS=' + agreements.size());

    passed = selectedCount >= 1 && informedConsentCount >= 1;
    if (!passed) {
        failureMessage = 'Expected selected agreement and Informed Consent to be created. selectedCount='
            + selectedCount + ', informedConsentCount=' + informedConsentCount + ', total=' + agreements.size();
    }
} catch (Exception e) {
    failureMessage = e.getTypeName() + ': ' + e.getMessage() + ' at line ' + e.getLineNumber();
}

Database.rollback(sp);

System.assert(passed, failureMessage);
System.debug('HEAL33418_SMOKE_RESULT=PASS');
