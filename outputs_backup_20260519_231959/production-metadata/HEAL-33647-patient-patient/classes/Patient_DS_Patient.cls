public with sharing class Patient_DS_Patient {
    @AuraEnabled
    public String firstName;
    @AuraEnabled
    public String lastName;
    @AuraEnabled
    public String email;
    @AuraEnabled
    public String phone;
    @AuraEnabled
    public String mobile;
    @AuraEnabled
    public String birthdate;
    @AuraEnabled
    public String gender;
    @AuraEnabled
    public Patient_DS_Address billingAddress;
    @AuraEnabled
    public Patient_DS_Address shippingAddress;
    @AuraEnabled
    public String biocanicPatientId;
    @AuraEnabled
    public String drChronoPatientId;
    @AuraEnabled
    public String drChronoPracticeGroupId;
    @AuraEnabled
    public String drChronoDoctorId;
    @AuraEnabled
    public String shopifyCustomerId;
    @AuraEnabled
    public Id salesforceId;
    @AuraEnabled
    public String accountStatus;
}