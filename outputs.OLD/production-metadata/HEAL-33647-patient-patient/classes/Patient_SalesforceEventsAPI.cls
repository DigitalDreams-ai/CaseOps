public with sharing class Patient_SalesforceEventsAPI extends RestClientLib {
	@TestVisible
	private static final String NAMED_CREDENTIAL_NAME = 'TenXAPI';

	public Patient_SalesforceEventsAPI(){
		this(NAMED_CREDENTIAL_NAME);
	}
	public Patient_SalesforceEventsAPI(String namedCredentialName){
		super(namedCredentialName != null ? namedCredentialName : NAMED_CREDENTIAL_NAME);
	}
	
	public void submitPatient(Patient_DS_Event event){
		try {
			Nebula.Logger.debug('Patient_SalesforceEventsAPI submitPatient Method.' + JSON.serialize(event));

			HttpResponse results = post('/salesforceevents', JSON.serialize(event));
			
			// Log Response
			Nebula.Logger.debug('Response from Patient_SalesforceEventsAPI :').setHttpResponseDetails(results);

			if(mc_QuiddityGuard.quiddityIsATestContext() && results.getStatusCode() >= 400){
				throw new IllegalArgumentException('Test thrown exception');
			}
		} catch (Exception genericException){
			Nebula.Logger.error('Patient_SalesforceEventsAPI submitPatient Method Exception :' + genericException);
		} finally {
			Nebula.Logger.saveLog();
		}
	}

	public void retryShopifyOrder(Shopify_DS_RetryOrders retryOrder) {
		try {
			Map<String, String> headers = new Map<String, String>();
			headers.put('Content-Type', 'application/json');
			headers.put('Content-Length', '0');
			headers.put('Accept', 'text/plain');
			Nebula.Logger.debug('Patient_SalesforceEventsAPI retryShopifyOrder Method.' + ' retryShopifyOrder ' + retryOrder.shop + ' retryOrder.skipAccountIdValidation ' + retryOrder.skipAccountIdValidation + ' retryOrder.skipFraudValidation ' + retryOrder.skipFraudValidation + ' retryOrder.accountId ' + retryOrder.accountId, retryOrder.caseid );

			HttpResponse results = post('/orders/shopify/resubmit-order', '?orderNumber=' + retryOrder.orderId + '&shop=' + retryOrder.shop + '&skipAccountIdValidation=' + retryOrder.skipAccountIdValidation + '&skipFraudValidation=' + retryOrder.skipFraudValidation + '&accountId=' + retryOrder.accountId, '', headers, false);
			
			// Log Response
			Nebula.Logger.debug('Response from Patient_SalesforceEventsAPI :' + retryOrder.orderId, retryOrder.caseid).setHttpResponseDetails(results);

			if(mc_QuiddityGuard.quiddityIsATestContext() && results.getStatusCode() >= 400){
				throw new IllegalArgumentException('Test thrown exception');
			}

		} catch (Exception genericException){
			Nebula.Logger.error('Patient_SalesforceEventsAPI retryShopifyOrder Method Exception :' + genericException);
		} finally {
			Nebula.Logger.saveLog();
		}
	}
	
}