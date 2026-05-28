public with sharing class Patient_AsyncAssignFormsApi implements System.Queueable, Database.AllowsCallouts {
	
	private final mc_Log logger = mc_Log.get();
	private final List<Patient_DS_ConsentForm_Request> batchOfConsentRequests;
	private final Id accountId;
	private final Patient_AssignFormsAPI apiWrapper = new Patient_AssignFormsAPI();
	
	public Patient_AsyncAssignFormsApi(List<Patient_DS_ConsentForm_Request> batchOfConsentRequests, Id accountId) {
		this.batchOfConsentRequests = batchOfConsentRequests;
		this.accountId = accountId;
	}
	
	public void execute(QueueableContext context) {
		try {
			for(Patient_DS_ConsentForm_Request consentRequest : batchOfConsentRequests) {
				apiWrapper.submitForms(consentRequest, accountId);
			}
		}
		/** catch (Exception genericException) {
			logger.add(genericException);
		} */
		finally {
			logger.publish();
		}
	}
}