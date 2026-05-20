public with sharing class Patient_AssignFormsAPI extends RestClientLib {
	@TestVisible
	private static final String NAMED_CREDENTIAL_NAME = 'TexXAssignFormsAPI';
	@TestVisible
	private final mc_Log logger = mc_Log.get();
	
	public Patient_AssignFormsAPI(){
		this(NAMED_CREDENTIAL_NAME);
	}
	
	public Patient_AssignFormsAPI(String namedCredentialName){
		super(namedCredentialName != null ? namedCredentialName : NAMED_CREDENTIAL_NAME);
	}
	
	public void submitForms(Patient_DS_ConsentForm_Request consentFormRequest, Id accountId) {
		try {
			// Instantiate a new http object
			Http h = new Http();
			HttpRequest req = new HttpRequest();
			req.setEndpoint('callout:TexXAssignFormsAPI' + '/patients/assignforms');
			req.setMethod('POST');
			req.setHeader('Content-Type', 'application/json');
			req.setBody(JSON.serialize(consentFormRequest));

			// Log Request
			Nebula.Logger.debug(' Sendign request to submit Biocanic Forms', accountId).setHttpRequestDetails(req);

			HttpResponse results = post('/patients/assignforms', JSON.serialize(consentFormRequest));
			// Log Response
			Nebula.Logger.debug('Response from submit Biocanic Forms', accountId).setHttpResponseDetails(results);

			if (results.getStatusCode() >= 400) {
				Nebula.Logger.error('Failed to assign Biocanic Form. See Response for error details.', accountId);
				return;
			}
			
			Patient_DS_ConsentForm_Response response = (Patient_DS_ConsentForm_Response) JSON.deserialize(results.getBody(), Patient_DS_ConsentForm_Response.class);
			List<Patient_Agreement__c> agreementsObjectsToUpdate = new List<Patient_Agreement__c>();
			
			for (Patient_DS_ConsentForm_ResponseItems item : response.items) {
				agreementsObjectsToUpdate.add(new Patient_Agreement__c(
						Id = item.salesforceAgreementId,
						Biocanic_Id__c = item.biocanicAssignmentId
				));
			}
			
			Nebula.Logger.debug('Updating Patient Agreement Biocanic Ids in Salesforce', agreementsObjectsToUpdate);
			
			Database.SaveResult[] saveResults = Database.update(agreementsObjectsToUpdate, false, AccessLevel.SYSTEM_MODE);
			Nebula.Logger.debug('Patient_SubmitForms: databaseUpdateResults ', saveResults);

		} catch (Exception genericException){
			Nebula.Logger.error('Error submitting Biocanic Forms', accountId, genericException);
		}
	}
}