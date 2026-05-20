public with sharing class Shopify_DS_RetryOrders {
    @AuraEnabled
    public String orderId;
    @AuraEnabled
    public String shop;
    @AuraEnabled
    public Boolean skipAccountIdValidation;
    @AuraEnabled
    public Boolean skipFraudValidation;
    @AuraEnabled
    public String caseId;
    @AuraEnabled
    public String accountId;
    @AuraEnabled
    public String opportunityId;
}