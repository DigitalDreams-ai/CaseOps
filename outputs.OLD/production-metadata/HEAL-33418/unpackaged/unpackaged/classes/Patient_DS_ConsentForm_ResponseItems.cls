public with sharing class Patient_DS_ConsentForm_ResponseItems {
    @AuraEnabled
    public String salesforceAgreementId;
    @AuraEnabled
    public String formId;
    @AuraEnabled
    public String biocanicAssignmentId;
    @AuraEnabled
    public Boolean success;
    @AuraEnabled
    public String errorMessage;
}