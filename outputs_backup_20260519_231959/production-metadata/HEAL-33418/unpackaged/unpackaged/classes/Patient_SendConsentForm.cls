public with sharing class Patient_SendConsentForm {
    @InvocableMethod(label='Send Biocanic Consent Forms' description='Send Biocanic Consent Forms' category='Patient')
    public static void Patient_SendConsentForm(List<Request> requests) {
        for(Request request : requests) {
            System.debug('Patient_SendConsentForm: ' + JSON.serializePretty(request.request));

            Id job = System.enqueueJob(new Patient_AsyncAssignFormsApi(request.request, request.accountId));
            System.debug('Patient_SendConsentForm: ' + job);
        }
    }

    public class Request {
        @InvocableVariable(label='Forms' description='APEX Defined form request' required=true)
        public List<Patient_DS_ConsentForm_Request> request;
        @InvocableVariable(label='Account Id' description='Account Id' required=true)
        public Id accountId;
    }

    public class Response {
        @InvocableVariable(label='Response' description='Response from the API')
        public Patient_DS_ConsentForm_Response response;
    }
}