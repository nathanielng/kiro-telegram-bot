# Follow-up: Bedrock Knowledge Base Integration for Chatbot

**From:** Tan Wei Jie <twjie@acmefinance.example.com>  
**To:** Alex Chen <achen@awsexample.com>  
**Date:** February 23, 2026, 4:32 PM  
**Subject:** Follow-up: Bedrock Knowledge Base Integration for Chatbot

Hi Alex,

Thanks for the detailed discussion last week about our customer service chatbot project. I've been reviewing the architecture you proposed and have a few follow-up questions.

**Current Situation:**
We've successfully deployed the basic chatbot using Bedrock's Claude model, but we're hitting limitations with our internal knowledge base integration. Our FAQ documents and policy manuals are stored across SharePoint, Confluence, and internal wikis.

**Questions:**
1. Can Bedrock Knowledge Base ingest documents from multiple sources simultaneously, or do we need to consolidate everything into S3 first?

2. For the vector database - you mentioned we could use either OpenSearch Serverless or the managed option. What's your recommendation for ~50,000 documents with weekly updates?

3. How does Bedrock KB handle document versioning? When we update a policy document, does it automatically re-index, or do we need to trigger that manually?

4. Regarding AgentCore integration - can the agent automatically decide when to query the Knowledge Base vs. when to use the Custom Model Import inference? Or do we need to explicitly define that logic?

5. What's the typical latency we should expect for KB queries? Our SLA requires responses within 3 seconds.

**Next Steps:**
If you have time next week, could we schedule a 30-minute call to walk through the KB setup process? I'd like to start a POC with a subset of our documents (around 5,000 files) before committing to the full migration.

Also, do you have any reference architectures or sample code for Bedrock KB + AgentCore integration? That would be incredibly helpful.

Thanks again for your support!

Best regards,  
Tan Wei Jie  
Head of Digital Transformation  
Acme Finance Pte Ltd  
twjie@acmefinance.example.com  
+65 6234 5678
