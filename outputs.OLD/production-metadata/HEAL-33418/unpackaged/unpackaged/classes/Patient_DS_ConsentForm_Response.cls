public with sharing class Patient_DS_ConsentForm_Response {
    @AuraEnabled
    public Boolean success;
    @AuraEnabled
    public String errorMessage;
    @AuraEnabled
    public List<Patient_DS_ConsentForm_ResponseItems> items;
}