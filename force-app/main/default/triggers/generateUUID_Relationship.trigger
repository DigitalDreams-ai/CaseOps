trigger generateUUID_Relationship on Relationship__c (before insert, before update) {
    for (Relationship__c relationship : Trigger.new) {
        if (relationship.UUID__c == null) { // Assuming you have a custom field UUID__c
            relationship.UUID__c = String.valueOf(UUID.randomUUID());
        }
    }
}