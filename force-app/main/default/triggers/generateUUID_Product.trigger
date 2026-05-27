/**
 * @description This trigger generates a UUID for a Product2 record if it doesn't already have one.
 * @apexTestClass generateUUID_TestSuite.testProductInsert
 */
trigger generateUUID_Product on Product2 (before insert, before update) {
    for (Product2 product : Trigger.new) {
        if (product.UUID__c == null) { // Assuming you have a custom field UUID__c
            product.UUID__c = String.valueOf(UUID.randomUUID());
        }
    }
}