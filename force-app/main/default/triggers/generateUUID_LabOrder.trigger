/**
 * @description This trigger generates a UUID for a Lab Order record if it doesn't already have one.
 * @apexTestClass generateUUID_TestSuite.testLabOrderInsert
 */
trigger generateUUID_LabOrder on Lab_Order__c (before insert, before update) {
    for (Lab_Order__c lo : Trigger.new) {
        if (lo.UUID__c == null) { // Assuming you have a custom field UUID__c
            lo.UUID__c = String.valueOf(UUID.randomUUID());
        }
    }
}