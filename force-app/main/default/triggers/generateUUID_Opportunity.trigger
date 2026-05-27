/**
 * @description This trigger generates a UUID for the Opportunity record if it doesn't already have one.
 * @apexTestClass generateUUID_TestSuite.testOpportunityInsert
 */
trigger generateUUID_Opportunity on Opportunity (before insert, before update) {
    for (Opportunity opp : Trigger.new) {
        if (opp.UUID__c == null) { // Assuming you have a custom field UUID__c
            opp.UUID__c = String.valueOf(UUID.randomUUID());
        }
    }
}