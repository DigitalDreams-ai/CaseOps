trigger LeadTrigger on Lead (before insert,before update) {
    
      Map<String,String> urlMap = new Map<String,String>{'hrt'=>'HRT','hormon'=>'HRT','identical'=>'HRT','testosterone'=>'HRT;Testosterone',
        												'sermorelin'=>'HRT;HGH','hgh'=>'HRT;HGH','peptide'=>'Peptides','pshot'=>'Sexual Health,P-Shot',
        										'p-shot'=>'Sexual Health,P-Shot','priapus'=>'Sexual Health,P-Shot','gainswave'=>'Sexual Health,GAINSWave'
       										 ,'gains-wave'=>'Sexual Health,GAINSWave','gw'=>'GAINSWave','erectile-dysfunction'=>'Sexual Health,ED Treatments'
        									,'gains-enhancement'=>'Sexual Health,GAINS Enhancement','male-enhancement'=>'Sexual Health','o-shot'=>'Sexual Health,O-Shot'
        									,'thermiva'=>'Sexual Health,Thermiva','thermismooth'=>'Aesthetics,Thermismooth','vampire'=>'Aesthetics,Vampire Facelift'
        					,'emsculpt'=>'Body Sculpting,EMSCULPT','peyronie'=>'Sexual Health,Peyronies Treatment','thyroid'=>'HRT;Thyroid'
        				,'trimix'=>'Sexual Health,Trimix','immunity'=>'Immunity','nad'=>'NAD','stem'=>'Stem Cells','exosome'=>'Exosomes','iv-therapy'=>'IV Therapy'
        				,'liquidvida'=>'IV Therapy','prp'=>'PRP','platelet'=>'PRP','wavetherapy.menshealthsystems.org'=>'Sexual Health,GAINSWave'};
    for(lead ld:Trigger.new)
    {
        String formUrl = ld.Form_URL__c;
		String formUrlLong = ld.Form_URL_Long__c;
        for(String str:urlMap.keySet())
        {
            if( ld.Form_URL__c !=null && ld.Form_URL__c.contains(str) )
            {
                String value = urlMap.get(str);
                if(!value.contains(';'))
                {
                    if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains(value))
                    {
                        if(ld.Visitor_Sessions_Interests__c == null)
                        {
                            ld.Visitor_Sessions_Interests__c = value;  
                        }else
                        {
                            ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+value;  
                        }
                        
                    }
                } else
                {
                    
                    list<String> values = value.split(';');
                    for(String val:values)
                    {
                        if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains(val))
                        {
                            if(ld.Visitor_Sessions_Interests__c == null)
                            {
                                ld.Visitor_Sessions_Interests__c = val;  
                            }else
                            {
                                ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+val;  
                            }
                            
                        } 
                    }
                    
                }                    
            }
            if( ld.Form_URL_Long__c !=null && ld.Form_URL_Long__c.contains(str)  )
            {
                String value = urlMap.get(str);
                if(!value.contains(';'))
                {
                    if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains(value))
                    {
                        if(ld.Visitor_Sessions_Interests__c == null) {  ld.Visitor_Sessions_Interests__c = value;  }else {  ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+value;  
                        }
                        
                    }
                } else
                {
                    
                    list<String> values = value.split(';');
                    for(String val:values)
                    {
                        if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains(val))
                        {
                            if(ld.Visitor_Sessions_Interests__c == null)
                            {
                                ld.Visitor_Sessions_Interests__c = val;  
                            }else
                            {
                                ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+val;  
                            }
                            
                        } 
                    }
                    
                }                    
            }
        }  
    }
    if(Trigger.isupdate)
    {
        for(lead ld:Trigger.new)
        {
            if(ld.status =='Convert To Patient' )
            {                 
                if(ld.email ==null ) {  ld.addError('Email is Required Field');
                                     }
            }
        }
    }
   
}