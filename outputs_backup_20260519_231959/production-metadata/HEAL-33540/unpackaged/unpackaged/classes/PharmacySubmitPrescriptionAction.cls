public without sharing class PharmacySubmitPrescriptionAction {
    @InvocableMethod(label='Submit Pharmacy Prescription Order' description='Sends the Pharmacy Prescription Order via 10X API Pharmacy API.' category='Account')
    public static List<Results> submitPharmacyPrescriptionOrder(List<Requests> requestsList) {
        List<Results> resultsList = new List<Results>();
        String calloutName = 'Wellvi_Submit_Prescription';
        for(Requests req : requestsList){
        	Nebula.Logger.debug('Starting Pharm Prescription callouts for the following record id: ' + req.recordId);
            try{
            	PharmacySubmitPrescriptionCallout pspc = new PharmacySubmitPrescriptionCallout(calloutName, req.recordId);
                Integer statusCode = pspc.invoke();
                Results res = new Results();
                res.statusCode = statusCode;
                resultsList.add(res);
            } catch(Exception e){
                //capture error and rethrow error to avoid user thinking transaction was successful
                Nebula.Logger.error(e.getMessage());
                Nebula.Logger.saveLog();  
                throw e;
            }
        }
        Nebula.Logger.saveLog();        
        return resultsList;
    }

    public class Requests{
        @InvocableVariable(label='Order Id' description='Id for Order to submit' required=true)
        public Id recordId;
    }

    public class Results{
        @InvocableVariable(label='Status Code Response' description='Status Code of the submission' required=true)
        public Integer statusCode;
    }
}