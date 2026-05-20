public with sharing class Patient_AsyncSalesforceEventsAPI implements System.Queueable, Database.AllowsCallouts {
	private final mc_Log logger = mc_Log.get();
	private final List<Patient_DS_Event> batchOfEvents;
	private final Patient_SalesforceEventsAPI apiWrapper = new Patient_SalesforceEventsAPI();
	public Patient_AsyncSalesforceEventsAPI(List<Patient_DS_Event> events){
		this.batchOfEvents = events;
	}
	public void execute(QueueableContext context) {
		try {
			for (Patient_DS_Event event :batchOfEvents){
				event.eventId = context.getJobId();
				apiWrapper.submitPatient(event);
			}
		}
		// this is commented out because I can't think of a situation in which context.getJobId() would throw an
		// exception, and because I know submitPatient doesn't throw an uncaptured exception.
		/** catch (Exception genericException) {
			logger.add(genericException);
		} */
		finally {
			logger.publish();
		}
	}
}