/**
 * @author Mark Gilbert
 * @date 9/8/2025
 * 
 * @group PharmacyAPI
 * @group-content ../../Utilities/Json
 * 
 * @description This class contains methods that are repeatable
 * for parsing JSON and building JSON.
 */

public with sharing class JsonUtility {

    /**
     * @description This method will build a Map<String,Object> to
     * adhere to a JSON style property mapping.
     * @param root Map<String,Object> of the object that will be converted to JSON
     * @param jsonPath Path of property in JSON. Format as '$.my.path'
     * @param value value that should be set for the final node of the jsonPath
     * @return void, root map will be modified instead of a return
     */
    public static void putByPath(Map<String,Object> root, String jsonPath, Object value){
        String path = jsonPath.startsWith('$.') ? jsonPath.substring(2) : jsonPath;
        List<String> nodes = path.split('\\.');
        Map<String, Object> nodeTree = root;
        for(Integer i = 0; i < nodes.size(); i++){
            String node = nodes[i];
            Boolean isLast = i == nodes.size()-1;
            
            if (isLast) {
                nodeTree.put(node, value);
            } else {
                if (!(nodeTree.get(node) instanceof Map<String,Object>)) {
                    nodeTree.put(node, new Map<String,Object>());
                }
                nodeTree = (Map<String,Object>) nodeTree.get(node);
            }
        }
    }
}