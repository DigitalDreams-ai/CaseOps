/**
 * @author Mark Gilbert
 * @date 8/29/2025
 * 
 * @group APIFramework
 * @group-content ../../API/APIFramework/APIOperation
 * 
 * @description This class is an abstract to allow for
 * APIs to be built on the API Operation and API
 * Parameters. Currently, the class is built for handling
 * POSTs and body parameters for POST methods. Will need
 * modification to support GET methods.
 */

//Ignore Apex CRUD warning as running without sharing
//Ignore cyclomatic complexity for now until I can resolve independent paths
@SuppressWarnings('PMD.ApexCRUDViolation, PMD.CyclomaticComplexity')
public without sharing abstract class ApiOperation {
    public String apiOperationName;
    public Id rootSObjectId;
    public Boolean callerSavingLog = false;
    protected API_Operation__mdt operation;
    protected List<API_Parameter__mdt> params;
    protected Map<String, Object> values;
    protected Map<String, Object> jsonBody;
    protected Map<String, String> requestHeaders;
    protected Map<String, Object> requestQuery;
    protected SObject rootRecord;
    
    /**
     * @description Initializes the API Operation for operations
     * that are not based on a record Id.
     * @param operationName The developer name of the API Operation metadata record.
     */
    public ApiOperation(String operationName){
        this.jsonBody = new Map<String, Object>();
        this.requestHeaders = new Map<String, String>();
        this.requestQuery = new Map<String, Object>();
        this.apiOperationName = operationName;
        getOperationByName();
        getParametersForOperation();
    } 
    
    
    /**
     * @description Initializes the API Operation for operations
     * that are for a record Id like a POST method.
     * @param operationName The developer name of the API Operation metadata record.
     * @param sourceSObjectId The record Id of the record that needs to be include with operation
     */
    public ApiOperation(String operationName, Id sourceSObjectId){
        this(operationName);
        if(String.isEmpty(sourceSObjectId)){
            throw new ApiOperationException('The calling Record Id is required to invoke this callout');
        }
        this.rootSObjectId = sourceSObjectId;
    }
    
    /**
     * @description Sets the body for the request based
     * on the parameters for the API Operation dynamically
     */
    protected void buildBody(){
        this.getSObjectDataForParams();
        this.getValuesForParameters();
        Nebula.Logger.debug('Params used for payload: ' + JSON.serializePretty(this.jsonBody));
    }

    /**
     * @description invoke the HTTPRequest and returns
     * the response.
     * @return HttpResponse
     */
    protected HttpResponse invokeCallout(){
        String endpoint = this.operation.Base_Named_Credential__c + this.operation.Path__c;
        HttpRequest request = new HttpRequest();
        request.setMethod(this.operation.HTTP_Method__c);
        request.setEndpoint(endpoint);

        if(!jsonBody.isEmpty()){
            request.setBody(JSON.serialize(this.jsonBody));
            request.setHeader('Content-Type', 'application/json');
        }

        if(this.operation.TimeoutMs__c != null){
            Integer timeout = Integer.valueOf(this.operation.TimeoutMs__c);
            request.setTimeout(timeout);
        }
		Nebula.Logger.debug('API Operation Request Information').setHttpRequestDetails(request);
        Http h = new Http();
        HttpResponse res = h.send(request);

		Nebula.Logger.debug('API Operation Response Information').setHttpResponseDetails(res);
        return res;
    }

    private void getSObjectDataForParams(){
        Set<String> selectArguments = new Set<String>();
        Map<String, List<String>> childFieldsBySObject = new Map<String, List<String>>();
        for(API_Parameter__mdt param : this.params){
            if(String.isNotEmpty(param.Field__c) && param.Data_Type__c != 'array'){
                selectArguments.add(param.Field__c);
            } else if(param.Data_Type__c == 'array'){
                if(!param.API_Child_Parameters__r.isEmpty()){
                    childFieldsBySObject.putAll(getFieldsFromChildParams(param));
                }
            }
        }
        if(!childFieldsBySObject.isEmpty()){
            for(String childRelation : childFieldsBySObject.keySet()){
                selectArguments.add('(SELECT ' + String.join(childFieldsBySObject.get(childRelation), ',') + ' FROM ' + childRelation + ')');
            }
        }
        
        String fullQuery = 'SELECT ' + String.join(selectArguments,',') + ' FROM ' + this.operation.Root_SObject__c + ' WHERE Id = \'' + this.rootSObjectId + '\'';
        
        Nebula.Logger.debug('Query for payload: ' + fullQuery);
        //Ignoring the PMD whitespace escape as we need to escape the single quote
        //This dynamic query built on the fields from CMT.
        this.rootRecord = Database.query(fullQuery); //NOPMD
    }
    

    //TODO Refactor code to fix standards and SOLID
    private void getValuesForParameters(){
        this.JsonBody = new Map<String, Object>();
        for(API_Parameter__mdt param : this.params){
            //TODO Change this to a switch to handle other locations
            if(param.Location__c == 'body'){
                setupBody(param, this.rootRecord);
            }
        }
    }
    
    private void getOperationByName(){
        List<API_Operation__mdt> operations = [SELECT Id,
                                               	Root_SObject__c,
                                                Base_Named_Credential__c,
                                                Path__c,
                                                HTTP_Method__c,
                                                TimeoutMs__c
                                              FROM API_Operation__mdt
                                              WHERE DeveloperName = :this.apiOperationName];
        
        if(operations.isEmpty() || operations.size() > 1){
            String improperAPIConfigMsg = 'Improperly configured API callout. Validate accuracy of API Operation Name';
            throw new ApiOperationException(improperAPIConfigMsg);
        } else{
            operation = operations[0];
        }
    }
    
    private void getParametersForOperation(){
        this.params = [SELECT Id,
                            Field__c,
                           	Data_Type__c,
                           	Location__c,
                           	IsRequired__c,
                            JSON_Path__c,
                            (SELECT API_Parameter__c,
                                Relation_Name__c,
                                Field__c,
                                Data_Type__c,
                                JSON_Path__c,
                                Override__c,
                                Override_Class__c,
                                Override_Method__c,
                                Override_Id_Field__c
                            FROM API_Child_Parameters__r)
                           FROM API_Parameter__mdt
                           WHERE API_Operation__c = :this.operation.Id];
        if(this.params == null || this.params.isEmpty()){
            String noAPIParamsMsg = 'No API Parameters defined for API Operation';
            throw new ApiOperationException(noAPIParamsMsg);
        }
    }

    private Map<String, List<String>> getFieldsFromChildParams(API_Parameter__mdt param){
        Map<String, List<String>> childFieldsBySObject = new Map<String, List<String>>();
        List<String> childFields = new List<String>();
        for(API_Child_Parameter__mdt childParam : param.API_Child_Parameters__r){
            if(!childParam.Override__c){
                if(childFieldsBySObject.containsKey(childParam.Relation_Name__c)){
                    childFieldsBySObject.get(childParam.Relation_Name__c).add(childParam.Field__c);
                } else{
                    childFieldsBySObject.put(childParam.Relation_Name__c, new List<String>{childParam.Field__c});
                }
            }
        }
        return childFieldsBySObject;
    }

    private void setupBody(API_Parameter__mdt param, SObject record){
        if(String.isNotEmpty(param.Field__c) && param.Location__c == 'body'){
            addParamToBody(param, record);
        } else if(param.Data_Type__c == 'array'){
            addParamArrayToBody(param, record);
        }
    }

    private void addParamToBody(API_Parameter__mdt param, SObject record){
        extractFieldValueToJsonPath(param.Field__c, record, param.JSON_Path__c, this.jsonBody);
    }

    private void addParamArrayToBody(API_Parameter__mdt param, SObject record){
        String relationName = param.API_Child_Parameters__r[0].Relation_Name__c;
        List<SObject> childObjects = record.getSObjects(relationName);
        if(childObjects != null && !childObjects.isEmpty()){
            List<Object> nestedJSON = new List<Object>();
            for(SObject childObject : childObjects){
                Map<String, Object> childJSON = new Map<String, Object>();
                for(API_Child_Parameter__mdt childParam : param.API_Child_Parameters__r){
                    if(childParam.Override__c){
                        Type className = Type.forName(childParam.Override_Class__c);
                        Object instance = className.newInstance();
                        Map<String, Object> arguments = new Map<String, Object>();
                        arguments.put(childParam.Override_Id_Field__c, childObject.get(childParam.Override_Id_Field__c));
                        Object value = ((Callable)instance).call(childParam.Override_Method__c, arguments);
                        JsonUtility.putByPath(childJSON, childParam.JSON_Path__c, value);
                    } else{
                        extractFieldValueToJsonPath(childParam.Field__c, childObject, childParam.JSON_Path__c, childJSON);
                    }
                }
                nestedJSON.add(childJSON);
            }
            String path = param.JSON_Path__c.startsWith('$.') ? param.JSON_Path__c.substring(2) : param.JSON_Path__c;
            this.jsonBody.put(path, nestedJSON);
        }
    }

    //Allowing the long list of parameters
    private void extractFieldValueToJsonPath(String fieldName, SObject record, String path, Map<String,Object> objMap){ //NOPMD
        List<String> fieldPath = fieldName.split('\\.');
        Object val;
        for(Integer i = 0; i < fieldPath.size(); i++){
            Boolean isLast = i == fieldPath.size() - 1;
            if(!isLast){
                if(record.getSObject(fieldPath[i]) == null){
                    break;
                }
                record = record.getSObject(fieldPath[i]);
            } else{
                val = record.get(fieldPath[i]);
                JsonUtility.putByPath(objMap, path, val);
            }
        }
        JsonUtility.putByPath(objMap, path, val);

    } 
    
    public class ApiOperationException extends Exception {}    
}