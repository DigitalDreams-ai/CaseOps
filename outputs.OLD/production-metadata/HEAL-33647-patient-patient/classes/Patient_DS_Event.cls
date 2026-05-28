public with sharing class Patient_DS_Event {
    @AuraEnabled
    public Id eventId; // This will be the loggers id
    @AuraEnabled
    public String eventType;
    @AuraEnabled
    public String data;
}