public with sharing class Patient_DS_ConsentForm_Request {
    @AuraEnabled
    public String accountId;
    @AuraEnabled
    public List<Patient_DS_ConsentForm_RequestForms> forms;
}