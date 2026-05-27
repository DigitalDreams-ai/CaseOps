/**
 * @description This trigger is used to generate a UUID for the Patient Agreement record
 * if it doesn't already have one.
 * @apexTestClass generateUUID_TestSuite.testPatientAgreementInsert
 */
trigger generateUUID_PatientAgreements on Patient_Agreement__c (before insert, before update) {
    for (Patient_Agreement__c pa : Trigger.new) {
        if (pa.UUID__c == null) { // Assuming you have a custom field UUID__c
            pa.UUID__c = String.valueOf(UUID.randomUUID());
        }
    }
}