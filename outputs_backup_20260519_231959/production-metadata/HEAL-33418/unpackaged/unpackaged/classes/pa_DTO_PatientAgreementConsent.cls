public class pa_DTO_PatientAgreementConsent {
    @AuraEnabled
    @InvocableVariable(required=true)
    public String patientAgreementConfigurationId;
    
    @AuraEnabled
    @InvocableVariable(required=true)
    public String patientAgreementId;
    
    @AuraEnabled
    @InvocableVariable(required=true)
    public String accountId;
    
    @AuraEnabled
    @InvocableVariable(required=false)
    public String opportunityId;
    
    @AuraEnabled
    @InvocableVariable(required=true)
    public pa_DTO_PatientAgreementSignature signature;
    
    @AuraEnabled
    @InvocableVariable(required=false)
    public List<pa_DTO_PatientAgreementAnswers> answers;

    // // Convert this object into a Map for JSON serialization
    // public Map<String, Object> toMap() {
    //     Map<String, Object> jsonMap = new Map<String, Object>();
    //     jsonMap.put('patientAgreementConfigurationId', patientAgreementConfigurationId);
    //     jsonMap.put('patientAgreementId', patientAgreementId);
    //     jsonMap.put('accountId', accountId);
    //     jsonMap.put('opportunityId', opportunityId);

    //     // Handle signature map
    //     Map<String, Object> signatureMap = new Map<String, Object>();
    //     signatureMap.put('patientName', signature.patientName);
    //     signatureMap.put('patientSignatureDate', signature.patientSignatureDate);
    //     signatureMap.put('patientEmail', signature.patientEmail);
    //     jsonMap.put('signature', signatureMap);

    //     // Handle answers list
    //     List<Map<String, Object>> answersList = new List<Map<String, Object>>();
    //     for (pa_DTO_PatientAgreementAnswers answer : answers) {
    //         Map<String, Object> answerMap = new Map<String, Object>();
    //         answerMap.put('key', answer.key);
    //         answerMap.put('value', answer.value);
    //         answersList.add(answerMap);
    //     }
    //     jsonMap.put('answers', answersList);

    //     return jsonMap;
    // }
}