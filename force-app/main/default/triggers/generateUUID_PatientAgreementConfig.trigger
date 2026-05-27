/**
 * @description This trigger is used to generate a UUID for the Patient Agreement Configuration record
 * if it doesn't already have one.
 * @apexTestClass generateUUID_TestSuite.testPatientAgreementConfigInsert
 */
trigger generateUUID_PatientAgreementConfig on Patient_Agreement_Configuration__c (before insert, before update) {
    for (Patient_Agreement_Configuration__c pac : Trigger.new) {
        if (pac.UUID__c == null) { // Assuming you have a custom field UUID__c
            pac.UUID__c = String.valueOf(UUID.randomUUID());
        }
    }
}