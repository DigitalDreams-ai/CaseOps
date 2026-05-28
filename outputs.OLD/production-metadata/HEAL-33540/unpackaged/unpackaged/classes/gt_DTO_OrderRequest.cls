public with sharing class gt_DTO_OrderRequest {
    @AuraEnabled
    public String lab_name;
    @AuraEnabled
    public String request_Type;
    @AuraEnabled
    public String request_ID;
    @AuraEnabled
    public String kit_ID;
    @AuraEnabled
    public String clinicID;
    @AuraEnabled
    public String requester_Name;
    @AuraEnabled
    public String clinic_Name;
    @AuraEnabled
    public String first_Name;
    @AuraEnabled
    public String last_Name;
    @AuraEnabled
    public String email;
    @AuraEnabled
    public String phone;
    @AuraEnabled
    public Date dob;
    @AuraEnabled
    public String gender;
    @AuraEnabled
    public String country;
    @AuraEnabled
    public String address1;
    @AuraEnabled
    public String address2;
    @AuraEnabled
    public String city;
    @AuraEnabled
    public String state;
    @AuraEnabled
    public String zip;
    @AuraEnabled
    public String comments;
    @AuraEnabled
    public Boolean bloodDraw;
    @AuraEnabled
    public String bloodDrawTests;
    @AuraEnabled
    public List<String> requested_items;
    //16 Jan 2026 Changes made for the story 20071
    @AuraEnabled
    public Decimal quantity;
    @AuraEnabled
    public Integer reshipAttempt;
    @AuraEnabled
    public String labProviderName;
    @AuraEnabled
    public Boolean demographicDataMandatory;
    @AuraEnabled
    public Double height;
    @AuraEnabled
    public Decimal weight;
    @AuraEnabled
    public String LabOrderId;
    @AuraEnabled
    public String PrecisionId;
    @AuraEnabled
    public String accountId;
    @AuraEnabled
    public Long patientId;
    @AuraEnabled
    public List<PatientAgreementRef> patientAgreements;

    public class PatientAgreementRef {
        @AuraEnabled
        public String id;

        public PatientAgreementRef() {}

        public PatientAgreementRef(String id) {
            this.id = id;
        }
    }
}