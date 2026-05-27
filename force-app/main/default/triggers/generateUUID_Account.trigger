/**
 * @description This trigger generates a UUID for the Account object before inserting or updating.
 * @apexTestClass generateUUID_TestSuite.testAccountInsert
 */
trigger generateUUID_Account on Account (before insert, before update) {
    for (Account acc : Trigger.new) {
        if (acc.UUID__c == null) { // Assuming you have a custom field UUID__c
            acc.UUID__c = String.valueOf(UUID.randomUUID());
        }
    }
}