trigger VisitorSessionTrigger on cloudamp__Visitor_Sessions__c (before insert) {
    
    Map<Id,set<String>> mapOfLead = new Map<Id,set<String>>();
    list<String> leadIds = new list<String>();
    for(cloudamp__Visitor_Sessions__c vs:Trigger.new)
    {
		leadIds.add(vs.cloudamp__Lead__c);
    }
    
    Map<id,lead> lds = new Map<id,lead>([SELECT Id, Visitor_Sessions_Interests__c FROM Lead WHERE id in :leadIds]);
    for(cloudamp__Visitor_Sessions__c vs:Trigger.new)
    {
        String url = vs.cloudamp__Page_URL__c;
        lead ld = lds.get(vs.cloudamp__Lead__c);
        if(url.contains('hrt') || url.contains('hormon')  || url.contains('identical') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('HRT'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'HRT';  
                }else
                {
                  ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'HRT';  
                }
                
            }
            
        }
        else if(url.contains('sermorelin') || url.contains('hgh') )
        {
            
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('HRT'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'HRT';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'HRT';  
                }                
            }
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('HGH'))
            {
                 if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'HGH';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'HGH';  
                }      
                
            }
        }
        else if(url.contains('testosterone') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('HRT'))
            {
                if(ld.Visitor_Sessions_Interests__c == null) {  ld.Visitor_Sessions_Interests__c = 'HRT';  
                }else  {    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'HRT';  
                }                
            } 
             if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Testosterone'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)  {  ld.Visitor_Sessions_Interests__c = 'Testosterone';  
                }else    {  ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Testosterone';  
                }                
            } 
        }
        else if(url.contains('peptide') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Peptides'))
            {
                if(ld.Visitor_Sessions_Interests__c == null) {  ld.Visitor_Sessions_Interests__c = 'Peptides';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Peptides';  
                }                
            } 
            
        }
        else if(url.contains('pshot')  || url.contains('p-shot')  || url.contains('priapus') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,P-Shot'))
            {
                if(ld.Visitor_Sessions_Interests__c == null) { ld.Visitor_Sessions_Interests__c = 'Sexual Health,P-Shot';  
                }else  { ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,P-Shot';  
                }                
            } 
            
        }
        else if(url.contains('gainswave')  || url.contains('gains-wave') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,GAINSWave'))
            {
                if(ld.Visitor_Sessions_Interests__c == null) {  ld.Visitor_Sessions_Interests__c = 'Sexual Health,GAINSWave';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,GAINSWave';  
                }                
            } 
            
        }
        else if(url.contains('gw') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('GAINSWave'))  { if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'GAINSWave';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'GAINSWave';  
                }                
            } 
            
        }
        else if(url.contains('erectile-dysfunction') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,ED Treatments'))
            {
                if(ld.Visitor_Sessions_Interests__c == null) {  ld.Visitor_Sessions_Interests__c = 'Sexual Health,ED Treatments';  
                }else  {  ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,ED Treatments';  
                }                
            } 
            
        }
        else if(url.contains('gains-enhancement') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,GAINS Enhancement'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)  { ld.Visitor_Sessions_Interests__c = 'Sexual Health,GAINS Enhancement';  
                }else  { ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,GAINS Enhancement';  
                }                
            } 
            
        }
        else if(url.contains('male-enhancement') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)  {   ld.Visitor_Sessions_Interests__c = 'Sexual Health';  
                }else {    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health';  
                }                
            } 
            
        }    
        else if(url.contains('o-shot') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,O-Shot'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)  { ld.Visitor_Sessions_Interests__c = 'Sexual Health,O-Shot';  
                }else   {   ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,O-Shot';  
                }                
            } 
            
        }    
        else if(url.contains('thermiva') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,Thermiva'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)  {  ld.Visitor_Sessions_Interests__c = 'Sexual Health,Thermiva';  
                }else  {   ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,Thermiva';  
                }                
            } 
            
        }   
        else if(url.contains('thermismooth') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Aesthetics,Thermismooth'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)   { ld.Visitor_Sessions_Interests__c = 'Aesthetics,Thermismooth';  
                }else  {    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Aesthetics,Thermismooth';  
                }                
            } 
            
        }   
        else if(url.contains('vampire') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Aesthetics,Vampire Facelift'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'Aesthetics,Vampire Facelift';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Aesthetics,Vampire Facelift';  
                }                
            } 
            
        }   
        else if(url.contains('emsculpt') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Body Sculpting,EMSCULPT'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'Body Sculpting,EMSCULPT';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Body Sculpting,EMSCULPT';  
                }                
            } 
            
        }   
        else if(url.contains('peyronie') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,Peyronies Treatment'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'Sexual Health,Peyronies Treatment';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,Peyronies Treatment';  
                }                
            } 
            
        }   
        else if(url.contains('thyroid') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('HRT,Thyroid'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'HRT,Thyroid';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'HRT,Thyroid';  
                }                
            } 
            
        }  
        else if(url.contains('trimix') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,Trimix'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'Sexual Health,Trimix';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,Trimix';  
                }                
            } 
            
        }  
        else if(url.contains('immunity') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Immunity'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'Immunity';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Immunity';  
                }                
            } 
            
        }  
        else if(url.contains('nad') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('NAD'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'NAD';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'NAD';  
                }                
            } 
            
        }  
        else if(url.contains('stem') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Stem Cells'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'Stem Cells';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Stem Cells';  
                }                
            } 
            
        }  
        else if(url.contains('exosome') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Exosomes'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'Exosomes';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Exosomes';  
                }                
            } 
            
        }
        else if(url.contains('iv-therapy') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('IV Therapy'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'IV Therapy';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'IV Therapy';  
                }                
            } 
            
        }
        else if(url.contains('liquidvida') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('IV Therapy'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'IV Therapy';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'IV Therapy';  
                }                
            } 
            
        }
        else if(url.contains('prp') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('PRP'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'PRP';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'PRP';  
                }                
            } 
            
        }
        else if(url.contains('platelet') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('PRP'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'PRP';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'PRP';  
                }                
            } 
            
        }
        else if(url.contains('wavetherapy.menshealthsystems.org') )
        {
            if(ld.Visitor_Sessions_Interests__c == null || !ld.Visitor_Sessions_Interests__c.contains('Sexual Health,GAINSWave'))
            {
                if(ld.Visitor_Sessions_Interests__c == null)
                {
                    ld.Visitor_Sessions_Interests__c = 'Sexual Health,GAINSWave';  
                }else
                {
                    ld.Visitor_Sessions_Interests__c = ld.Visitor_Sessions_Interests__c + ';'+'Sexual Health,GAINSWave';  
                }                
            } 
            
        }
        lds.put(ld.Id, ld );
    } 
    update lds.values();

}