/**
 * @author Mark Gilbert
 * @date 8/29/2025
 * 
 * @group PharmacyAPI
 * @group-content ../../API/PharmacyAPI/SubmitPrescription
 * 
 * @description This class will be used to POST to the Submit Prescription on
 * the 10X API to submit prescription orders to the proper pharmacy. This class
 * purposely runs without sharing as we will want access to all values for the 
 * payload even if the running user does not have access.
 */

//Ignore Apex CRUD warning as running without sharing
@SuppressWarnings('PMD.ApexCRUDViolation')
public without sharing class PharmacySubmitPrescriptionCallout extends ApiOperation{
    
    /**
     * @description Constructor to implement the callout method. It will initialize
     * the payload based on the related API Operation metadata record.
     * @param name The developer name of the API Operation metadata record.
     * @param orderId The Id of the Order record that is being processed.
     */
    public PharmacySubmitPrescriptionCallout(String name, Id orderId){
        super(name, orderId);
        if(!this.isInvokedForOrder()){
            throw new ApiOperationException('Pharmacy Submit Prescription only supports Order as a root object');
        }
        this.buildBody();
    }
    
    /**
     * @description Invokes the callout that was initialized in the constructor
     * and will update the Order Items with the results from the callout.
     * @return Integer The status code of the response
     */
    public Integer invoke(){
        HttpResponse response = this.invokeCallout();
        updateOrderItemsBasedOnResponse(response);
        Nebula.Logger.debug('Pharmacy Submit Prescription callout status code' + response.getStatusCode());
        Nebula.Logger.debug('Pharmacy Submit Prescription callout response: ' + response.getBody());
        return response.getStatusCode();
    }

    /**
     * @description This method will update the Order Items based on the results
     * from the callout. It will determine the mapping of response results to
     * order items based on the National Drug Code.
     * @param response The response that is returned by the invoked callout
     */
    private void updateOrderItemsBasedOnResponse(HttpResponse response){
        if(response.getStatusCode() == 400){
            this.replicateErrorToAllOrderItems(response.getBody());
        } else{
            SubmitPrescriptionResponse spr = (SubmitPrescriptionResponse)JSON.deserialize(response.getBody(), SubmitPrescriptionResponse.class);
            if(spr.prescriptionResults != null && !spr.prescriptionResults.isEmpty()){
                List<String> ndcs = new List<String>();
                for(PrescriptionResults result : spr.prescriptionResults){
                    if(String.isNotEmpty(result.nationalDrugCode)){
                        ndcs.add(result.nationalDrugCode);
                    }
                }
                Map<String, OrderItem> orderItemsByNdc = getOrderItemsByNdc(ndcs);
                List<OrderItem> itemsToUpdate = getOrderItemsToUpdateFromResults(spr.prescriptionResults, orderItemsByNdc);
                update itemsToUpdate;
            }
        }
    }

    private void replicateErrorToAllOrderItems(String errorMessage){
        List<OrderItem> childItems = [SELECT Id
                                        FROM OrderItem
                                        WHERE OrderId = :this.rootSObjectId];
        for(OrderItem childItem : childItems){
            childItem.isError__c = true;
            childItem.Status__c = 'Transmission Error';
            childItem.ErrorMessage__c = errorMessage;
        }
        update childItems;
    }

    private Map<String, OrderItem> getOrderItemsByNdc(List<String> ndcs){
        Map<String, OrderItem> orderItemsByNdc = new Map<String, OrderItem>();
        List<OrderItem> items = [SELECT Id,
                                    PricebookEntry.NDC__c
                                FROM OrderItem
                                WHERE PricebookEntry.NDC__c IN :ndcs
                                AND OrderId = :this.rootSObjectId];
        for(OrderItem item : items){
            orderItemsByNdc.put(item.PricebookEntry.NDC__c, item);
        }

        return orderItemsByNdc;
    }

    private List<OrderItem> getOrderItemsToUpdateFromResults(List<PrescriptionResults> results, Map<String, OrderItem> orderItemsByNdc){
        List<OrderItem> itemsToUpdate = new List<OrderItem>();
        for(PrescriptionResults result : results){
            if(String.isNotEmpty(result.nationalDrugCode)){
                if(orderItemsByNdc.containsKey(result.nationalDrugCode)){
                    OrderItem item = orderItemsByNdc.get(result.nationalDrugCode);
                    putResultOnOrderItem(result, item);
                    itemsToUpdate.add(item);
                }
            }
        }
        return itemsToUpdate;
    }

    private void putResultOnOrderItem(PrescriptionResults result, OrderItem item){
        item.ExternalPrescriptionId__c = result.rxId;
        if(doesResultHaveError(result)){
            item.isError__c = true;
            item.Status__c = 'Transmission Error';
            item.ErrorMessage__c = result.errors[0];
        }
    }

    private Boolean isInvokedForOrder(){
        String objectAPIName = this.rootSObjectId.getSObjectType().getDescribe().getName();
        return (objectAPIName == 'Order');   
    }

    private Boolean doesResultHaveError(PrescriptionResults result){
        return (result.errors != null && !result.errors.isEmpty());
    }
    
    public class SubmitPrescriptionResponse{
        public List<PrescriptionResults> prescriptionResults;
    }

    public class PrescriptionResults{
        public String nationalDrugCode;
        public String rxId;
        public String result;
        public List<String> errors;
    }
}