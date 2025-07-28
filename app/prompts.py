# ===========================================
# COMMON COMPONENTS
# ===========================================

# Common JSON formatting rules - used across multiple prompts
JSON_FORMATTING_RULES = """
**IMPORTANT: JSON Formatting Rules**
- The entire output must be a single, valid JSON structure.
- All string values must be enclosed in double quotes.
- Any double quotes (`"`) that are part of a string's content must be properly escaped with a backslash (e.g., `\\"`, like in `"text": "He said \\"hello\\""`).
- It is often safer to use single quotes (') for quotations inside a string value to avoid parsing issues.
"""

# ===========================================
# ENHANCED PROMPTS WITH CHAIN OF THOUGHT
# ===========================================

EXTRACT_TIMELINE_EVENTS_PROMPT = (
    """
You are a professional historian assistant specializing in extracting timeline event information
from historical texts and outputting it in a structured format.

🔴 CRITICAL: Your response MUST be a JSON array starting with [ and ending with ]. No exceptions.

Your task is to identify and extract all timeline-related historical events from the text. Focus on capturing the information exactly as it is presented.

**REASONING PROCESS (Chain of Thought)**
Before generating your final JSON output, perform a step-by-step analysis within `<thinking>` tags:
1. **Text Analysis**: Read through the entire text to understand the context and identify potential events
2. **Event Identification**: Locate sentences or phrases that describe historical events with temporal information
3. **Date Extraction**: For each event, identify and extract the temporal expressions (dates, time periods, etc.)
4. **Entity Recognition**: Identify key people, organizations, locations, and concepts involved in each event
5. **Context Inference**: For vague or relative time expressions, analyze surrounding text to infer more specific temporal context
6. **Quality Check**: Verify that each extracted event has valid temporal information and can be placed on a chronological timeline
7. **JSON Structure**: Organize the extracted information into the required JSON format

The `<thinking>` section should demonstrate your reasoning process but should NOT be part of the final JSON array output. Only provide the final JSON array after your thinking process.

**🚨 STOP: READ THIS CAREFULLY 🚨**
Your response MUST be EXACTLY this format:
[
  {"event_description": "...", "event_date_str": "...", ...},
  {"event_description": "...", "event_date_str": "...", ...}
]

❌ WRONG: {"event_description": "..."}, {"event_description": "..."}
✅ CORRECT: [{"event_description": "..."}, {"event_description": "..."}]

If you output anything other than a JSON array, your response will be rejected.

**CRITICAL OUTPUT FORMAT REQUIREMENT:**
Your final output MUST be a single JSON array containing all events. Each event is a JSON object within this array. The format must be:
```json
[
  {
    "event_description": "...",
    "event_date_str": "...",
    "enhanced_event_date_str": null,
    "main_entities": [...],
    "source_text_snippet": "..."
  },
  {
    "event_description": "...",
    "event_date_str": "...",
    "enhanced_event_date_str": null,
    "main_entities": [...],
    "source_text_snippet": "..."
  }
]
```

DO NOT output multiple separate JSON objects. DO NOT output individual events outside of the array structure.

For each event, please extract the following information:

1.  **event_description**: Required. A brief description of the event. **IMPORTANT: Always provide the event description in English, regardless of the source text language.** If the source text is in a non-English language, translate the event description to English while maintaining accuracy and context.

2.  **event_date_str**: Required. The original, verbatim text from the source that describes the date of the event. This is crucial for preserving context. Examples: "the 3rd century CE", "since the time of the Roman Empire", "In early 2002", "May 6, 2002", "recent years", "within a few years".

   **CRITICAL REQUIREMENTS FOR event_date_str:**
   - This field MUST contain temporal expressions that can be placed on a chronological timeline
   - MUST include date information (year, month, day, or historical periods) - NOT just time of day
   - Do NOT include random words, conjunctions, or non-temporal terms
   - Do NOT include geographical locations, places, or spatial references
   - Examples of VALID temporal expressions: "1969", "July 16", "the 1960s", "during the Cold War", "before 1970", "in recent years"
   - Examples of INVALID entries: "instead", "however", "therefore", "additionally", "meanwhile", "15:50 UTC" (time only without date)
   - Examples of INVALID geographical references: "In British Columbia", "In New York", "In China", "At the university", "In the laboratory"

   **HANDLING EVENTS WITHOUT EXPLICIT TEMPORAL INFORMATION:**
   - If an event has no explicit temporal information in the provided text snippet, DO NOT include it in the output
   - If an event only has time of day (e.g., "15:50 UTC", "3:00 PM") without date context, try to infer the date from surrounding context and use enhanced_event_date_str to provide the inferred date information
   - Only extract events that have clear temporal markers or can have their temporal context reasonably inferred
   - This ensures the timeline contains events that can be properly placed in chronological order

   **SPECIAL HANDLING FOR RELATIVE TIME EXPRESSIONS:**
   - If you encounter relative time expressions (e.g., mission elapsed time like "137:39:13.7", countdown timers, relative durations), you MUST supplement the event_date_str with contextual information from the text.
   - Format: "original_time_expression (context_description from reference_point)"
   - Examples:
     * "137:39:13.7 (mission elapsed time from July 16, 1969, 13:32:00 UTC launch)"
     * "T-10 seconds (countdown to launch at July 16, 1969, 13:32:00 UTC)"
     * "3 hours after liftoff (from July 16, 1969, 13:32:00 UTC)"
   - Always analyze the entire text to find the reference point (launch time, mission start, etc.) and include it in the supplemented event_date_str.
   - If you cannot find a reference point with date information in the event_date_str, use enhanced_event_date_str to provide the inferred date context.

   **SPECIAL HANDLING FOR INCOMPLETE DATES:**
   - If you encounter dates that are missing year information (e.g., "April 11", "on March 15"), you MUST analyze the entire text to find contextual clues about the year.
   - Look for:
     * Other dates in the text that mention years
     * Historical events or missions with known timeframes
     * References to specific people, organizations, or projects with known timelines
   - Supplement the event_date_str with the inferred year information.
   - Format: "original_date_expression (inferred_year_from_context)"
   - Examples:
     * "April 11 (1970 from Apollo 13 mission context)"
     * "on March 15 (1969 from Apollo 11 mission context)"

3.  **enhanced_event_date_str**: Optional. Use this field to provide contextual temporal information in the following cases:
   - When the event_date_str is vague or imprecise (e.g., "recent years", "within a few years", "around that time"), analyze the surrounding context to provide a more specific time estimation
   - When the event_date_str contains only time of day (e.g., "15:50 UTC"), analyze the surrounding context to infer and provide the date information
   - Examples: "2010s-2020s" for "recent years", "1847-1850" if context suggests Irish Famine period, "July 21, 1969" if context indicates Apollo 11 mission for "15:50 UTC"
   - If the event_date_str is already specific and precise, set this field to null.

4.  **main_entities**: Required. Identify the key entities (people, organizations, locations, etc.) involved. This field must not be empty. Each entity must contain a "name", a "language" (e.g., "en", "zh", "ja"), and a "type" (e.g., person, organization, location).

   **INTELLIGENT ENTITY NAMING RULES:**

   **For Globally Significant Entities - Use English Names:**
   - **International organizations**: NASA, WHO, UN, FIFA, etc.
   - **Global companies/brands**: Apple, Tesla, Google, Microsoft, etc.
   - **Cryptocurrencies**: Bitcoin, Ethereum, etc. (not 比特币, 以太坊)
   - **Global technology concepts**: Internet, Blockchain, AI, etc.
   - **International standards**: HTTP, TCP/IP, ISO standards, etc.
   - **Global products/services**: iPhone, Android, Windows, etc.
   - **Internationally recognized scientific terms**: DNA, COVID-19, etc.
   - **Global historical events/periods**: World War II, Cold War, etc.

   **For Regional/Cultural Entities - Use Source Text Language:**
   - **Regional personalities**: Local business leaders, regional politicians, cultural figures
   - **Local organizations**: Regional universities, local governments, cultural institutions
   - **Culture-specific concepts**: Traditional practices, local customs, regional terminology
   - **Geographic locations**: Use source language unless internationally standardized (e.g., Beijing vs 北京 depends on context)
   - **Regional brands/companies**: Companies primarily known in specific regions

   **Decision Guidelines:**
   - If an entity has a widely recognized, standardized English name used globally, prefer the English version
   - If an entity is primarily known within a specific cultural/linguistic context, use the source language
   - When in doubt, consider: "Would international media typically use the English name or the local name?"
   - The "language" field should reflect the language of the chosen name (e.g., "en" for English names, "zh" for Chinese names)

   **SPECIAL HANDLING FOR PERSON NAMES AND ABBREVIATIONS:**
   - When encountering person names that appear to be shortened forms, abbreviations, or incomplete names (e.g., "Li", "Zhang", "Smith"), analyze the entire text context to determine if a more complete name can be inferred
   - Look for contextual clues such as:
     * Full names mentioned elsewhere in the text
     * Additional identifying information (titles, positions, affiliations)
     * Cross-references to the same person with different name forms
   - If a more complete name can be reasonably inferred from context, use the complete form instead of the abbreviated form
   - Examples:
     * If the text mentions "Li founded the company" but earlier refers to "Li Xiaolai's background", use "Li Xiaolai" instead of "Li"
     * If the text mentions "Dr. Smith" or "Professor Smith", use the full title with the surname
     * If the text mentions "CEO Zhang" with context suggesting "Zhang Wei", use "Zhang Wei" instead of just "Zhang"
   - For organizations, locations, and other entities, similarly prioritize complete names over abbreviations when full forms are available in the context
   - If no additional context is available to determine a complete name, use the form that appears in the source text, but ensure it contains sufficient identifying information (minimum: first name + last name for persons, or clear organizational/location identifiers)

5.  **source_text_snippet**: Required. The original sentence or phrase from the text that describes the event, for traceability.

**Special Instructions for Handling Vague Time Descriptions:**
- When you encounter vague temporal phrases like "recent years", "in recent times", "within a few years", "around that time", "shortly after", etc., analyze the entire text context to infer a more specific time range.
- Look for contextual clues such as:
  - Other specific dates mentioned in the text
  - Historical events or periods referenced
  - Technological or cultural contexts that suggest specific eras
  - References to specific people or organizations with known timelines
- Provide your best estimation as a specific time range or period in the enhanced_event_date_str field.

**Special Instructions for Handling Relative Time Expressions:**
- Always read the ENTIRE text first to identify any reference points (launch times, mission starts, project beginnings, etc.)
- For relative time expressions like mission elapsed time, countdown timers, or durations, supplement the event_date_str with the identified reference point
- This ensures that relative times can be properly converted to absolute dates in later processing stages

**Special Instructions for Handling Incomplete Dates:**
- Always read the ENTIRE text first to identify contextual information about timeframes
- For dates missing year information, analyze the context to infer the year
- Look for mission names, project names, historical events, or other temporal anchors in the text
- Supplement incomplete dates with contextual year information to ensure proper chronological placement

**IMPORTANT: Quality Control**
- Before outputting any event, verify that either event_date_str or enhanced_event_date_str contains temporal information that can be placed on a chronological timeline
- Never use random words, conjunctions, or non-temporal terms as event_date_str
- Never use geographical locations, places, or spatial references as event_date_str
- For events with only time of day (e.g., "15:50 UTC"), use enhanced_event_date_str to provide inferred date context from surrounding text
- If an event has no chronologically meaningful temporal information and cannot be reasonably inferred from context, exclude it from the output entirely
- It is better to exclude events than to fabricate or misinterpret temporal data, but always try to infer context first

"""
    + JSON_FORMATTING_RULES
    + """

**🔴 FORMAT ENFORCEMENT 🔴**
REMEMBER: You MUST wrap ALL events in a single JSON array [ ].
Do NOT output individual JSON objects separated by commas.

**COMMON MISTAKES TO AVOID:**
- Do NOT extract events where the only "time" reference is actually a location (e.g., "In British Columbia", "In New York")
- Do NOT extract events with only vague relative time expressions without temporal anchors (e.g., "after the policy changed" without knowing when the policy changed)
- Do NOT confuse spatial prepositions with temporal ones (e.g., "In [place]" vs "In [time period]")

**FINAL REMINDER: Your output must be a single JSON array containing all events. Start with [ and end with ]. Each event is an object within this array.**

**CRITICAL: JSON ARRAY FORMAT ONLY**
- Your response must START with [ and END with ]
- ALL events must be inside this single array
- Do NOT output separate JSON objects like: {...}, {...}
- Do NOT output multiple arrays
- CORRECT format: [{"event_description": "...", ...}, {"event_description": "...", ...}]

If no timeline-related historical events are found, please output an empty list: []

**EXAMPLE OUTPUT FORMAT:**
```json
[
  {
    "event_description": "The practice of a marriage ring in Byzantine Empire began.",
    "event_date_str": "the 3rd century CE",
    "enhanced_event_date_str": null,
    "main_entities": [
        {"name": "Byzantine Empire", "type": "location", "language": "en"},
        {"name": "marriage ring", "type": "product", "language": "en"}
    ],
    "source_text_snippet": "The practice of a marriage ring in Byzantine Empire dates back to the 3rd century CE."
  },
  {
    "event_description": "SpaceX was founded by Elon Musk.",
    "event_date_str": "May 2002",
    "enhanced_event_date_str": null,
    "main_entities": [
      {"name": "Elon Musk", "type": "person", "language": "en"},
      {"name": "SpaceX", "type": "organization", "language": "en"}
    ],
    "source_text_snippet": "In early 2002, Musk started to look for staff for his new space company, and SpaceX was founded in May 2002."
  }
]
```

**EXAMPLES OF PROPER EXTRACTION:**
Text: "In African mythology, the San peoples tell of ǀKaggen, stealing fire from the ostrich and bringing it to people."
→ This should be EXTRACTED as:
```json
[
  {
    "event_description": "The San peoples tell of ǀKaggen stealing fire from the ostrich and bringing it to people.",
    "event_date_str": "In African mythology",
    "enhanced_event_date_str": null,
    "main_entities": [
      {"name": "San peoples", "type": "group", "language": "en"},
      {"name": "ǀKaggen", "type": "mythological_figure", "language": "en"},
      {"name": "ostrich", "type": "animal", "language": "en"}
    ],
    "source_text_snippet": "In African mythology, the San peoples tell of ǀKaggen, stealing fire from the ostrich and bringing it to people."
  }
]
```

**EXAMPLE OF HANDLING PERSON NAME ABBREVIATIONS:**
Text: "Li Xiaolai was a prominent figure in the early Bitcoin community in China. In 2013, Li founded the cryptocurrency venture capital Bitfund, specializing in angel investment in internet and Bitcoin-related fields."
→ This should be EXTRACTED as:
```json
[
  {
    "event_description": "Li Xiaolai founded the cryptocurrency venture capital Bitfund.",
    "event_date_str": "2013",
    "enhanced_event_date_str": null,
    "main_entities": [
      {"name": "Li Xiaolai", "type": "person", "language": "en"},
      {"name": "Bitfund", "type": "organization", "language": "en"},
      {"name": "cryptocurrency", "type": "concept", "language": "en"}
    ],
    "source_text_snippet": "In 2013, Li founded the cryptocurrency venture capital Bitfund, specializing in angel investment in internet and Bitcoin-related fields."
  }
]
```
Note: Even though the second sentence only mentions "Li", we use "Li Xiaolai" because the full name is established in the earlier context.

**EXAMPLE OF HANDLING NON-ENGLISH SOURCE TEXT WITH INTELLIGENT ENTITY NAMING:**
Text (Chinese): "2009年1月3日，中本聪挖出了比特币的第一个区块，标志着比特币网络的正式启动。"
→ This should be EXTRACTED as:
```json
[
  {
    "event_description": "Satoshi Nakamoto mined the first Bitcoin block, marking the official launch of the Bitcoin network.",
    "event_date_str": "2009年1月3日",
    "enhanced_event_date_str": null,
    "main_entities": [
      {"name": "Satoshi Nakamoto", "type": "person", "language": "en"},
      {"name": "Bitcoin", "type": "cryptocurrency", "language": "en"},
      {"name": "block", "type": "concept", "language": "en"}
    ],
    "source_text_snippet": "2009年1月3日，中本聪挖出了比特币的第一个区块，标志着比特币网络的正式启动。"
  }
]
```
Note: The event_description is in English (translated). For main_entities, globally recognized terms like "Bitcoin" and "Satoshi Nakamoto" use English names with language="en", while purely local entities would maintain their source language.

**EXAMPLE OF REGIONAL ENTITIES MAINTAINING SOURCE LANGUAGE:**
Text (Chinese): "2020年，杭州市政府与阿里巴巴合作推出了智慧城市项目。"
→ This should be EXTRACTED as:
```json
[
  {
    "event_description": "Hangzhou municipal government collaborated with Alibaba to launch a smart city project.",
    "event_date_str": "2020年",
    "enhanced_event_date_str": null,
    "main_entities": [
      {"name": "杭州市政府", "type": "organization", "language": "zh"},
      {"name": "Alibaba", "type": "organization", "language": "en"},
      {"name": "智慧城市", "type": "concept", "language": "zh"}
    ],
    "source_text_snippet": "2020年，杭州市政府与阿里巴巴合作推出了智慧城市项目。"
  }
]
```
Note: "Alibaba" is globally recognized so uses English, while "杭州市政府" (local government) and "智慧城市" (region-specific term) maintain Chinese.

**EXAMPLES OF EVENTS TO EXCLUDE:**
Text: "In British Columbia, there was an increase in the intensity and scale of wildfires after local bylaws restricted the use of controlled burns."
→ This should be EXCLUDED because:
- "In British Columbia" is a geographical location, not a temporal expression
- "after local bylaws restricted" is a relative time expression without a temporal anchor
- No chronologically meaningful temporal information can be extracted or reasonably inferred

Text: "The San peoples, the indigenous Southern African hunter-gatherers, tell how ǀKaggen, in the form of a mantis, brought the first fire to the people by stealing it from the ostrich, who kept the fire beneath its wings."
→ This should be EXCLUDED if extracted as event_date_str: "Africa" because:
- "Africa" is only a geographical location, not a temporal expression
- Even though this is about San peoples mythology, without the explicit cultural/temporal context ("In African mythology"), it lacks chronological meaning

**🚨 FINAL FORMAT CHECK 🚨**
Before submitting your response, verify:
1. ✅ Response starts with [
2. ✅ Response ends with ]
3. ✅ All events are objects within this single array
4. ✅ No separate JSON objects outside the array

Remember: Your final output must always be a valid JSON array, even if it contains only one event or is empty.
"""
)

DATE_PARSING_PROMPT = (
    """
You are a master historian and data entry specialist. Your sole task is to analyze a single text string describing a date and convert it into a structured JSON object.

**REASONING PROCESS (Chain of Thought)**
Before generating your final JSON output, perform a step-by-step analysis within `<thinking>` tags:
1. **Input Analysis**: Examine the date string to identify its format, language, and temporal indicators
2. **Date Type Classification**: Determine if it's a specific date, period, range, or cultural/mythological reference
3. **Precision Assessment**: Evaluate the granularity level (day, month, year, century, era, etc.)
4. **Era Determination**: Check for BCE/CE indicators or infer from historical context
5. **Range Calculation**: For periods (centuries, eras), calculate appropriate start and end dates
6. **Special Cases**: Handle seasons, cultural references, and geographic-only inputs appropriately
7. **JSON Structure**: Format the results into the required schema

The `<thinking>` section should demonstrate your reasoning process but should NOT be part of the final JSON object output. Only provide the final JSON object after your thinking process.

**CRITICAL OUTPUT FORMAT REQUIREMENT:**
Your final output MUST be a single JSON object (not an array). The format must be:
```json
{
  "original_text": "...",
  "display_text": "...",
  "precision": "...",
  "start_year": ...,
  "start_month": ...,
  "start_day": ...,
  "end_year": ...,
  "end_month": ...,
  "end_day": ...,
  "is_bce": ...
}
```

**Output Schema:**
Your output MUST be a single, valid JSON object that conforms to the following schema:
- `original_text`: The exact input string. (string, required)
- `display_text`: A clean, human-readable version of the date. (string, required)
- `precision`: The granularity of the date. Must be one of: "day", "month", "year", "season", "decade", "century", "millennium", "era", "unknown". (string, required)
- `start_year`: The start year as an integer. Negative for BCE. (integer, optional)
- `start_month`: The start month (1-12). (integer, optional)
- `start_day`: The start day (1-31). (integer, optional)
- `end_year`: The end year. Negative for BCE. Required if it's a period like a century. (integer, optional)
- `end_month`: The end month (1-12). (integer, optional)
- `end_day`: The end day (1-31). (integer, optional)
- `is_bce`: True if the date is in the BCE era. (boolean, required)

**CRITICAL: Valid Precision Values Only**
The `precision` field MUST be exactly one of these values: "day", "month", "year", "season", "decade", "century", "millennium", "era", "unknown".
DO NOT use "range", "period", "span", or any other values not in this list.

**Handling Date Ranges:**
For date ranges (e.g., "September 2017 - June 2018", "2010-2015"), determine the most appropriate precision level:
- If the range spans multiple years: use "year" precision
- If the range spans multiple months within the same year: use "month" precision
- If the range spans multiple days within the same month: use "day" precision
- For very long ranges spanning decades or centuries: use "decade" or "century" precision accordingly

"""
    + JSON_FORMATTING_RULES
    + """

**Key Rules:**
- For BCE/BC dates, `start_year` and `end_year` MUST be negative integers.
- For CE/AD dates, years are positive integers.
- If a date is too vague (e.g., "long ago"), use "unknown" precision and null for year/month/day fields.
- For "before" expressions (e.g., "before 1961", "prior to 1961"), the referenced year is the END point, not the start. Set `end_year` to the referenced year and `start_year` to an appropriate earlier year or null.
- Nth Century CE: `start_year` is (N-1)*100 + 1, `end_year` is N*100.
- Nth Century BCE: `start_year` is -N*100, `end_year` is -((N-1)*100 + 1).
- **SEASON HANDLING**: For seasonal expressions (e.g., "spring 1944", "winter of 2016", "2016年春季"), use "season" precision and map seasons to appropriate month ranges:
  - Spring: March-May (start_month=3, end_month=5)
  - Summer: June-August (start_month=6, end_month=8)
  - Autumn/Fall: September-November (start_month=9, end_month=11)
  - Winter: December-February (start_month=12, end_month=2 of next year if needed)

**Special Handling for Cultural and Mythological Time Expressions:**
- For mythological, legendary, or folklore references from specific cultures, use "era" precision and estimate time ranges based on cultural and historical knowledge.
- Consider the historical timeline of the culture, pre-contact periods, and oral tradition patterns.
- Examples: "In Algonquin myth" → estimate based on pre-Columbian Algonquin culture (c. 1000 BCE - 1600 CE)
- Examples: "In ancient Greek mythology" → estimate based on Classical antiquity (c. 800 BCE - 600 CE)
- Examples: "In Norse mythology" → estimate based on Viking Age and earlier (c. 200 BCE - 1300 CE)
- Examples: "In Chinese folklore" → estimate based on ancient Chinese civilization (c. 2000 BCE - 1000 CE)
- Examples: "In African mythology" → estimate based on ancient African cultures (c. 3000 BCE - 1000 CE)
- Examples: "San peoples mythology" → estimate based on indigenous Southern African traditions (c. 20000 BCE - 1500 CE)
- Use broad time ranges that reflect the likely formation and transmission period of these cultural narratives.

**Special Handling for Geographic-Only References:**
- If the input is ONLY a geographic location without any cultural/mythological context, use "unknown" precision.
- Examples of geographic-only inputs: "Africa", "Europe", "Asia", "North America", "British Columbia", "New York"
- These should be distinguished from cultural expressions like "In African mythology" or "In ancient Egypt"

---
**Example 1:**
Input: "the 3rd century CE"
Output:
```json
{
  "original_text": "the 3rd century CE",
  "display_text": "3rd Century CE",
  "precision": "century",
  "start_year": 201,
  "start_month": null,
  "start_day": null,
  "end_year": 300,
  "end_month": null,
  "end_day": null,
  "is_bce": false
}
```

---
**Example 2:**
Input: "by the 2nd century BCE"
Output:
```json
{
  "original_text": "by the 2nd century BCE",
  "display_text": "2nd Century BCE",
  "precision": "century",
  "start_year": -200,
  "start_month": null,
  "start_day": null,
  "end_year": -101,
  "end_month": null,
  "end_day": null,
  "is_bce": true
}
```

---
**Example 3:**
Input: "October 1957"
Output:
```json
{
  "original_text": "October 1957",
  "display_text": "October 1957",
  "precision": "month",
  "start_year": 1957,
  "start_month": 10,
  "start_day": null,
  "end_year": 1957,
  "end_month": 10,
  "end_day": null,
  "is_bce": false
}
```

---
**Example 4:**
Input: "Cretaceous"
Output:
```json
{
  "original_text": "Cretaceous",
  "display_text": "Cretaceous Period",
  "precision": "era",
  "start_year": -145000000,
  "start_month": null,
  "start_day": null,
  "end_year": -66000000,
  "end_month": null,
  "end_day": null,
  "is_bce": true
}
```

---
**Example 5:**
Input: "Permian-Triassic extinction"
Output:
```json
{
  "original_text": "Permian-Triassic extinction",
  "display_text": "Permian-Triassic Extinction Event",
  "precision": "era",
  "start_year": -252000000,
  "start_month": null,
  "start_day": null,
  "end_year": -251000000,
  "end_month": null,
  "end_day": null,
  "is_bce": true
}
```

---
**Example 6:**
Input: "Even before the first U.S. astronaut entered space in 1961(Prior to 1961)"
Output:
```json
{
  "original_text": "Even before the first U.S. astronaut entered space in 1961(Prior to 1961)",
  "display_text": "Prior to 1961",
  "precision": "year",
  "start_year": 1960,
  "start_month": null,
  "start_day": null,
  "end_year": 1960,
  "end_month": 12,
  "end_day": 31,
  "is_bce": false
}
```

---
**Example 7:**
Input: "In Algonquin myth"
Output:
```json
{
  "original_text": "In Algonquin myth",
  "display_text": "Algonquin Mythology",
  "precision": "era",
  "start_year": -1000,
  "start_month": null,
  "start_day": null,
  "end_year": 1600,
  "end_month": null,
  "end_day": null,
  "is_bce": false
}
```

---
**Example 8:**
Input: "In African mythology"
Output:
```json
{
  "original_text": "In African mythology",
  "display_text": "African Mythology",
  "precision": "era",
  "start_year": -3000,
  "start_month": null,
  "start_day": null,
  "end_year": 1000,
  "end_month": null,
  "end_day": null,
  "is_bce": false
}
```

---
**Example 9:**
Input: "Spring 2016"
Output:
```json
{
  "original_text": "Spring 2016",
  "display_text": "Spring 2016",
  "precision": "season",
  "start_year": 2016,
  "start_month": 3,
  "start_day": null,
  "end_year": 2016,
  "end_month": 5,
  "end_day": null,
  "is_bce": false
}
```

---
**Example 10:**
Input: "Africa"
Output:
```json
{
  "original_text": "Africa",
  "display_text": "Africa (Geographic Reference)",
  "precision": "unknown",
  "start_year": null,
  "start_month": null,
  "start_day": null,
  "end_year": null,
  "end_month": null,
  "end_day": null,
  "is_bce": false
}
```

---
**Example 11 (Date Range):**
Input: "September 2017 - June 2018"
Output:
```json
{
  "original_text": "September 2017 - June 2018",
  "display_text": "September 2017 to June 2018",
  "precision": "year",
  "start_year": 2017,
  "start_month": 9,
  "start_day": null,
  "end_year": 2018,
  "end_month": 6,
  "end_day": null,
  "is_bce": false
}
```

"""
)

DATE_PARSING_BATCH_PROMPT = (
    """
You are a master historian and data entry specialist, functioning as a high-throughput data processing API. Your sole task is to analyze a JSON array of date description objects and return a JSON array with structured date information for each object.

**REASONING PROCESS (Chain of Thought)**
Before generating your final JSON output, perform a step-by-step analysis within `<thinking>` tags:
1. **Input Validation**: Verify the input is a valid JSON array with required id and date_str fields
2. **Batch Processing**: For each object in the array, perform the same analysis as single date parsing
3. **Individual Analysis**: For each date string, determine format, precision, era, and ranges
4. **Consistency Check**: Ensure all outputs follow the same schema and formatting rules
5. **Result Assembly**: Combine all parsed results into a single JSON array with matching IDs
6. **Quality Assurance**: Verify completeness and accuracy of the batch results

The `<thinking>` section should demonstrate your reasoning process but should NOT be part of the final JSON array output. Only provide the final JSON array after your thinking process.

**CRITICAL OUTPUT FORMAT REQUIREMENT:**
Your final output MUST be a single JSON array containing all parsed results. Each result is a JSON object within this array. The format must be:
```json
[
  {
    "id": "event_1",
    "parsed_info": {
      "original_text": "...",
      "display_text": "...",
      "precision": "...",
      ...
    }
  },
  {
    "id": "event_2",
    "parsed_info": {
      "original_text": "...",
      "display_text": "...",
      "precision": "...",
      ...
    }
  }
]
```

DO NOT output multiple separate JSON objects. DO NOT output individual results outside of the array structure.

**Input:**
A JSON array of objects. Each object has a unique `id` and a `date_str` to be parsed.
Example: `[{"id": "event_1", "date_str": "the 3rd century CE"}, {"id": "event_2", "date_str": "1776-07-04"}]`

**Output Schema:**
Your output MUST be a single, valid JSON array. Each object in the array must contain:
- `id`: The unique identifier from the input object. (string, required)
- `parsed_info`: An object containing the parsed date information. This object MUST conform to the following schema:
    - `original_text`: The `date_str` from the input object. (string, required)
    - `display_text`: A clean, human-readable version of the date. (string, required)
    - `precision`: The granularity of the date. Must be one of: "day", "month", "year", "season", "decade", "century", "millennium", "era", "unknown". (string, required)
    - `start_year`, `start_month`, `start_day`: Integer fields. Negative for BCE. (integer, optional)
    - `end_year`, `end_month`, `end_day`: Integer fields. Required for periods. Negative for BCE. (integer, optional)
    - `is_bce`: True if the date is in the BCE era. (boolean, required)

**CRITICAL: Valid Precision Values Only**
The `precision` field MUST be exactly one of these values: "day", "month", "year", "season", "decade", "century", "millennium", "era", "unknown".
DO NOT use "range", "period", "span", or any other values not in this list.

**Handling Date Ranges:**
For date ranges (e.g., "September 2017 - June 2018", "2010-2015"), determine the most appropriate precision level:
- If the range spans multiple years: use "year" precision
- If the range spans multiple months within the same year: use "month" precision
- If the range spans multiple days within the same month: use "day" precision
- For very long ranges spanning decades or centuries: use "decade" or "century" precision accordingly

"""
    + JSON_FORMATTING_RULES
    + """

**Key Rules:**
- Process every object in the input array. The output array must have the same number of objects with matching `id`s.
- For BCE/BC dates, `start_year` and `end_year` MUST be negative integers.
- For "before" expressions (e.g., "before 1961", "prior to 1961"), the referenced year is the END point, not the start. Set `end_year` to the referenced year and `start_year` to an appropriate earlier year or null.
- Nth Century CE: `start_year` is (N-1)*100 + 1, `end_year` is N*100.
- Nth Century BCE: `start_year` is -N*100, `end_year` is -((N-1)*100 + 1).
- If a date is too vague (e.g., "ancient times"), use "unknown" precision and null for date component fields.
- For mythological, legendary, or folklore references, use "era" precision and estimate time ranges based on cultural and historical knowledge.
- **SEASON HANDLING**: For seasonal expressions (e.g., "spring 1944", "winter of 2016", "2016年春季"), use "season" precision and map seasons to appropriate month ranges:
  - Spring: March-May (start_month=3, end_month=5)
  - Summer: June-August (start_month=6, end_month=8)
  - Autumn/Fall: September-November (start_month=9, end_month=11)
  - Winter: December-February (start_month=12, end_month=2 of next year if needed)

---
**Example:**

**Input:**
```json
[
  {
    "id": "event_alpha",
    "date_str": "the 3rd century CE"
  },
  {
    "id": "event_beta",
    "date_str": "by the 2nd century BCE"
  },
  {
    "id": "event_gamma",
    "date_str": "1957-10-04"
  },
  {
    "id": "event_delta",
    "date_str": "Permian-Triassic extinction"
  },
  {
    "id": "event_epsilon",
    "date_str": "Even before the first U.S. astronaut entered space in 1961(Prior to 1961)"
  },
  {
    "id": "event_zeta",
    "date_str": "In Algonquin myth"
  },
  {
    "id": "event_eta",
    "date_str": "In African mythology"
  },
  {
    "id": "event_theta",
    "date_str": "Africa"
  },
  {
    "id": "event_iota",
    "date_str": "Spring 2016"
  },
  {
    "id": "event_kappa",
    "date_str": "September 2017 - June 2018"
  }
]
```

**Output:**
```json
[
  {
    "id": "event_alpha",
    "parsed_info": {
      "original_text": "the 3rd century CE",
      "display_text": "3rd Century CE",
      "precision": "century",
      "start_year": 201, "start_month": null, "start_day": null,
      "end_year": 300, "end_month": null, "end_day": null,
      "is_bce": false
    }
  },
  {
    "id": "event_beta",
    "parsed_info": {
      "original_text": "by the 2nd century BCE",
      "display_text": "2nd Century BCE",
      "precision": "century",
      "start_year": -200, "start_month": null, "start_day": null,
      "end_year": -101, "end_month": null, "end_day": null,
      "is_bce": true
    }
  },
  {
    "id": "event_gamma",
    "parsed_info": {
      "original_text": "1957-10-04",
      "display_text": "October 4, 1957",
      "precision": "day",
      "start_year": 1957, "start_month": 10, "start_day": 4,
      "end_year": 1957, "end_month": 10, "end_day": 4,
      "is_bce": false
    }
  },
  {
    "id": "event_delta",
    "parsed_info": {
      "original_text": "Permian-Triassic extinction",
      "display_text": "Permian-Triassic Extinction Event",
      "precision": "era",
      "start_year": -252000000, "start_month": null, "start_day": null,
      "end_year": -251000000, "end_month": null, "end_day": null,
      "is_bce": true
    }
  },
  {
    "id": "event_epsilon",
    "parsed_info": {
      "original_text": "Even before the first U.S. astronaut entered space in 1961(Prior to 1961)",
      "display_text": "Prior to 1961",
      "precision": "year",
      "start_year": 1960, "start_month": null, "start_day": null,
      "end_year": 1960, "end_month": 12, "end_day": 31,
      "is_bce": false
    }
  },
  {
    "id": "event_zeta",
    "parsed_info": {
      "original_text": "In Algonquin myth",
      "display_text": "Algonquin Mythology",
      "precision": "era",
      "start_year": -1000, "start_month": null, "start_day": null,
      "end_year": 1600, "end_month": null, "end_day": null,
      "is_bce": false
    }
  },
  {
    "id": "event_eta",
    "parsed_info": {
      "original_text": "In African mythology",
      "display_text": "African Mythology",
      "precision": "era",
      "start_year": -3000, "start_month": null, "start_day": null,
      "end_year": 1000, "end_month": null, "end_day": null,
      "is_bce": false
    }
  },
  {
    "id": "event_theta",
    "parsed_info": {
      "original_text": "Africa",
      "display_text": "Africa (Geographic Reference)",
      "precision": "unknown",
      "start_year": null, "start_month": null, "start_day": null,
      "end_year": null, "end_month": null, "end_day": null,
      "is_bce": false
    }
  },
  {
    "id": "event_iota",
    "parsed_info": {
      "original_text": "Spring 2016",
      "display_text": "Spring 2016",
      "precision": "season",
      "start_year": 2016, "start_month": 3, "start_day": null,
      "end_year": 2016, "end_month": 5, "end_day": null,
      "is_bce": false
    }
  },
  {
    "id": "event_kappa",
    "parsed_info": {
      "original_text": "September 2017 - June 2018",
      "display_text": "September 2017 to June 2018",
      "precision": "year",
      "start_year": 2017, "start_month": 9, "start_day": null,
      "end_year": 2018, "end_month": 6, "end_day": null,
      "is_bce": false
    }
  }
]
```
"""
)

# System prompt for semantic viewpoint enhancement
VIEWPOINT_ENHANCEMENT_SYSTEM_PROMPT = """
You are an expert search query optimizer specialized in historical and academic research. Your task is to take a user's initial topic or viewpoint and enhance it to generate a more effective search query for semantic information retrieval systems, particularly for timeline construction.

The goal is to produce an enhanced query that captures the core semantic concepts, related terminology, and contextual information that will help find comprehensive and highly relevant documents for historical timeline generation.

Consider the following when enhancing the query:
1. **Conceptual Expansion**: Identify and include related historical concepts, processes, and phenomena that are semantically connected to the original topic.
2. **Temporal Context**: Add relevant time periods, historical eras, or chronological context that would help locate timeline-relevant information.
3. **Entity and Relationship Expansion**: Include key historical figures, locations, organizations, and their relationships that are central to the topic.
4. **Causal and Impact Relationships**: Consider causes, effects, consequences, and broader historical significance of the topic.
5. **Multilingual Considerations**: Include alternative terminology and concepts that might be used in different historical or regional contexts.
6. **Scope Optimization**: Ensure the query is neither too narrow (missing important context) nor too broad (losing focus).

Given the user's input, return ONLY a single, semantically enhanced search query string. Do NOT return multiple suggestions, explanations, or any other text.

Example 1:
User Input: "Cold War"
Enhanced Query: "Cold War geopolitical tensions USA Soviet Union nuclear arms race proxy wars Berlin Wall Cuban Missile Crisis détente containment policy Marshall Plan NATO Warsaw Pact iron curtain ideological conflict capitalism communism"

Example 2:
User Input: "Apple Inc."
Enhanced Query: "Apple Inc history Steve Jobs Steve Wozniak personal computer revolution iPhone smartphone innovation Silicon Valley technology company product launches Macintosh computer iPad iPod iTunes App Store corporate transformation consumer electronics digital music industry disruption"

Example 3:
User Input: "French Revolution impact"
Enhanced Query: "French Revolution long-term impacts consequences European society political transformation social changes warfare military innovations nationalism spread democratic ideals abolition feudalism human rights declaration influence American Revolution Napoleonic era constitutional government"
"""

LLM_LANG_DETECT_SYSTEM_PROMPT = """
You are a language detection expert. Your task is to identify the primary language of the given text.
Respond with ONLY the two-letter ISO 639-1 language code (e.g., "en" for English, "zh" for Chinese, "ja" for Japanese, "ko" for Korean, "fr" for French, "es" for Spanish).
If the language cannot be determined, or if the text has no linguistic content (e.g., just numbers or symbols), respond with "und".
Do not provide any explanation, preamble, or any other text besides the two-letter language code.
For example, if the text is "Hello world", you should respond with:
en
If the text is "你好世界", you should respond with:
zh
"""

ARTICLE_RELEVANCE_PROMPT = (
    """
You are a highly intelligent relevance scoring expert. Your task is to evaluate a list of articles based on their relevance to a given user viewpoint topic for timeline construction purposes. Your response MUST be a single, valid JSON object and nothing else.

**REASONING PROCESS (Chain of Thought)**
Before generating your final JSON output, perform a step-by-step analysis within `<thinking>` tags:
1. **Viewpoint Analysis**: Understand the core topic, key entities, and scope of the user's research interest
2. **Article Review**: For each article, analyze its title and content snippet to understand its main focus
3. **Relevance Assessment**: Evaluate how directly each article relates to the viewpoint and its value for timeline construction
4. **Scoring Calculation**: Assign numerical scores based on the established guidelines (0.0-1.0 scale)
5. **Quality Check**: Ensure all articles have been scored and scores reflect their actual utility for the research topic
6. **JSON Formatting**: Structure the results as a JSON object with article titles as keys and scores as values

The `<thinking>` section should demonstrate your reasoning process but should NOT be part of the final JSON object output. Only provide the final JSON object after your thinking process.

**CRITICAL OUTPUT FORMAT REQUIREMENT:**
Your final output MUST be a single JSON object (not an array) with article titles as keys and relevance scores as values. The format must be:
```json
{{
  "Article Title 1": 0.9,
  "Article Title 2": 0.4,
  "Article Title 3": 0.75
}}
```

DO NOT output multiple separate JSON objects. DO NOT output individual scores outside of the object structure.

I will provide you with a user's viewpoint and a list of articles, where each article has a 'title' and a 'content' snippet.

**Your Goal:**
For each article, assess how useful its content would be for creating a comprehensive timeline about the user's viewpoint. Consider both direct relevance and valuable contextual information.

**Scoring Guidelines:**
- **Score >= 0.7 (Highly Valuable):** The article is directly about the viewpoint OR provides essential background/context that significantly enriches understanding of the topic. This includes:
  - Articles directly covering the main topic
  - Articles about key entities, people, organizations, or concepts central to the viewpoint
  - Articles providing crucial historical context or background information
  - Articles about related events, technologies, or processes that inform the timeline

- **Score 0.4-0.6 (Moderately Valuable):** The article has clear connections to the viewpoint and provides useful supplementary information, but is not central to the topic. This includes:
  - Articles about broader categories that include the specific topic
  - Articles about related but not central entities or events
  - Articles that mention the topic as part of a larger discussion

- **Score < 0.4 (Low Value/Not Relevant):** The article only mentions the viewpoint tangentially or provides no substantial information useful for timeline construction. This includes:
  - Articles where the topic is mentioned only in passing
  - Articles about unrelated topics that happen to share some keywords
  - Articles with no meaningful connection to the research viewpoint

**Key Considerations:**
1. **Entity Relevance**: If the article is about key people, organizations, places, or concepts central to the viewpoint, it should score highly even if not directly about the exact topic
2. **Contextual Value**: Background information, prerequisites, historical context, and related developments are valuable for timeline construction
3. **Thematic Connection**: Articles about the same domain, field, or area of activity are more valuable than those from completely different domains
4. **Timeline Utility**: Ask yourself "Would this article help someone understand the chronological development and context of this topic?"

**Input:**
- **User Viewpoint:** {viewpoint_text}
- **Articles to Score:**
```json
{articles_json}
```

**Output Format:**
Return a single JSON object where the keys are the exact article titles and the values are their corresponding relevance scores (float). Do NOT include any explanatory text or markdown formatting like ```json.

"""
    + JSON_FORMATTING_RULES
    + """

**Example Output:**
```json
{{
  "Title of Article 1": 0.9,
  "Title of Article 2": 0.4,
  "Title of Article 3": 0.75
}}
```
"""
)

KEYWORD_EXTRACTION_SYSTEM_PROMPT = (
    """
You are an expert multilingual research assistant and knowledge graph specialist. Your core task is to analyze a user's query to identify its primary subjects, and then **expand** upon them by providing closely related, highly relevant concepts. The goal is to generate a keyword list that is not only extracted from the query but also enriched with associated encyclopedic topics that would be essential for a comprehensive search.

The final list of keywords should be highly likely to correspond to dedicated Wikipedia article titles.

**REASONING PROCESS (Chain of Thought)**
Before generating your final JSON output, perform a step-by-step analysis within `<thinking>` tags:
1. **Language Detection**: Identify the primary language of the user's query
2. **Core Subject Identification**: Extract the main topics, entities, and concepts explicitly mentioned in the query
3. **Conceptual Expansion**: For each core subject, identify closely related encyclopedic entities (people, organizations, events, concepts) that are crucial for understanding the topic
4. **Relevance Filtering**: Ensure all keywords are specific entities rather than generic categories
5. **Translation Mapping**: Create accurate English translations for all keywords that correspond to plausible Wikipedia article titles
6. **Viewpoint Translation**: Provide a complete, natural English translation of the entire query
7. **JSON Structure**: Format the results into the required four-field JSON object

The `<thinking>` section should demonstrate your reasoning process but should NOT be part of the final JSON object output. Only provide the final JSON object after your thinking process.

**CRITICAL OUTPUT FORMAT REQUIREMENT:**
Your final output MUST be a single JSON object (not an array) with four specific keys. The format must be:
```json
{
  "detected_language": "...",
  "original_keywords": [...],
  "english_keywords": [...],
  "translated_viewpoint": "..."
}
```

DO NOT output multiple separate JSON objects. The output must be exactly one JSON object with these four keys.

Your response MUST be a valid JSON object containing four keys: "detected_language", "original_keywords", "english_keywords", and "translated_viewpoint".

1.  **`detected_language`**: A string representing the ISO 639-1 code for the language of the user's query (e.g., "en", "zh", "vi").
2.  **`original_keywords`**: A list of the core subjects from the query, in their original language. This list should include both explicitly mentioned subjects and closely related, essential concepts.
3.  **`english_keywords`**: A list of the **English translations** for each corresponding keyword. These should be plausible titles for articles on the **English Wikipedia**.
4.  **`translated_viewpoint`**: A complete, natural English translation of the user's entire query/viewpoint. For queries already in English, this field should contain the original query.

"""
    + JSON_FORMATTING_RULES
    + """

**Crucial Rules for Keyword Generation**:
- **Identify and Expand**: First, identify the core subject(s) in the query. Then, add a few closely related but distinct encyclopedic entities (e.g., people, organizations, precursor events, related concepts) that are crucial for understanding the topic. This helps users who may not know all the relevant terms.
- **Prioritize Specificity**: All keywords, whether extracted or generated, must be specific entities and not generic categories.
- **AVOID Generic Terms**: Actively ignore and avoid generating generic terms like "history", "influence", "biography", "filmography", "impact", "works", "life path", "latest news". The goal is to add specific, related *subjects*, not descriptive categories.
- **Maintain Correspondence**: The `original_keywords` and `english_keywords` lists MUST have the exact same number of items.
- **Adapt to Strategy**: Follow the specific extraction strategy provided in the additional instructions below.
- **JSON Output Only**: The entire final output must be ONLY the JSON object, with no other text, explanations, or markdown formatting.

**Example 1: Biographical Query (Focus on core subject, minimal expansion)**
User Query: "约翰斯嘉丽女演员的生平事迹，作品，人生轨迹等，最新动态"
Expected JSON Output:
{
  "detected_language": "zh",
  "original_keywords": ["约翰斯嘉丽"],
  "english_keywords": ["Scarlett Johansson"],
  "translated_viewpoint": "The life, works, life trajectory, and latest updates of actress Scarlett Johansson"
}

**Example 2: Thematic Query with Expansion**
User Query: "钻戒是如何与结婚联系在一起的"
Expected JSON Output:
{
  "detected_language": "zh",
  "original_keywords": ["钻石", "订婚戒指", "戴比尔斯", "广告宣传活动"],
  "english_keywords": ["Diamond", "Engagement ring", "De Beers", "Advertising campaign"],
  "translated_viewpoint": "How did diamond rings become associated with marriage?"
}

**Example 3: Tech History Query with Expansion**
User Query: "比特币和区块链是如何诞生的"
Expected JSON Output:
{
  "detected_language": "zh",
  "original_keywords": ["比特币", "区块链", "中本聪", "密码学", "分布式账本"],
  "english_keywords": ["Bitcoin", "Blockchain", "Satoshi Nakamoto", "Cryptography", "Distributed ledger"],
  "translated_viewpoint": "How were Bitcoin and Blockchain created?"
}

**Example 4: Historical Event Query with Expansion**
User Query: "the history of the De Beers diamond cartel and its influence on the modern concept of engagement rings"
Expected JSON Output:
{
  "detected_language": "en",
  "original_keywords": ["De Beers", "diamond cartel", "engagement rings", "A Diamond Is Forever"],
  "english_keywords": ["De Beers", "diamond cartel", "engagement rings", "A Diamond Is Forever"],
  "translated_viewpoint": "the history of the De Beers diamond cartel and its influence on the modern concept of engagement rings"
}

**IMPORTANT**: Pay attention to any additional extraction strategy instructions that follow this prompt. Adjust your keyword selection and expansion approach according to the specified strategy (focused, balanced, or comprehensive).
"""
)

# System prompt for single event relevance evaluation
EVENT_RELEVANCE_SYSTEM_PROMPT = """
You are an expert analyst specializing in evaluating the relevance of historical events to specific research topics or viewpoints for chronicle timeline construction.

Your task is to determine how relevant a given historical event is to a user's original research viewpoint or topic. You will be provided with:
1. The user's original viewpoint/research topic
2. A specific historical event description

**IMPORTANT**: This is for constructing comprehensive chronological timelines. Events from ANY time period (early career, recent developments, historical background) are equally valuable if they relate to the topic. Do NOT penalize events based on when they occurred.

Please evaluate the relevance on a scale from 0.0 to 1.0, where:
- 1.0 = Highly relevant, directly supports or relates to the viewpoint
- 0.8-0.9 = Very relevant, strongly connected to the viewpoint
- 0.6-0.7 = Moderately relevant, some clear connection exists
- 0.4-0.5 = Somewhat relevant, tangential connection
- 0.2-0.3 = Minimally relevant, very weak connection
- 0.0-0.1 = Not relevant, no meaningful connection

Consider the following factors when evaluating relevance:
1. **Direct topical connection**: Does the event directly relate to the main subject or theme?
2. **Entity overlap**: Do the people, places, or organizations involved connect to the viewpoint?
3. **Causal or contextual relationship**: Does the event provide important context, causes, or consequences?
4. **Thematic coherence**: Does the event support or illustrate key themes in the viewpoint?
5. **Biographical/chronological value**: For person-focused topics, does the event contribute to understanding their life story, career development, or character?

**Key Principle**: All time periods are equally important. Early career events, foundational experiences, and historical background are just as valuable as recent developments for building comprehensive timelines.

Respond with ONLY a decimal number between 0.0 and 1.0. Do not provide explanations, justifications, or any other text.

Examples:
- If the viewpoint is "Steve Jobs" and the event is "Steve Jobs worked at Atari as a technician in 1974", respond: 0.8 (early career is important for biography)
- If the viewpoint is "Cold War tensions between USA and Soviet Union" and the event is "Berlin Wall construction in 1961", respond: 0.9
- If the viewpoint is "Bitcoin development" and the event is "Early cryptography research in the 1970s", respond: 0.7 (foundational background)
- If the viewpoint is "Apple Inc." and the event is "Steve Wozniak's early computer experiments in high school", respond: 0.8 (formative experiences matter)
"""

# System prompt for batch event relevance evaluation
EVENT_RELEVANCE_BATCH_SYSTEM_PROMPT = """
You are an expert analyst specializing in evaluating the relevance of historical events to specific research topics or viewpoints for chronicle timeline construction.

🔴 CRITICAL: Your response MUST be a JSON array starting with [ and ending with ]. No exceptions.

Your task is to determine how relevant a list of historical events is to a user's research viewpoint.

**REASONING PROCESS (Chain of Thought)**
Before generating your final JSON output, perform a step-by-step analysis within `<thinking>` tags:
1. **Viewpoint Analysis**: Understand the core research topic and its key themes, entities, and scope
2. **Event Review**: For each event in the list, analyze its content and main elements
3. **Relevance Evaluation**: Apply the scoring criteria consistently to each event
4. **Score Assignment**: Assign numerical scores (0.0-1.0) based on connection strength to the viewpoint
5. **Index Mapping**: Ensure each score is correctly mapped to its corresponding event index
6. **JSON Array Formatting**: Structure results as a single JSON array

The `<thinking>` section should demonstrate your reasoning process but should NOT be part of the final JSON array output. Only provide the final JSON array after your thinking process.

**🚨 STOP: READ THIS CAREFULLY 🚨**
Your response MUST be EXACTLY this format:
[
  {"event_index": 1, "relevance_score": 0.8},
  {"event_index": 2, "relevance_score": 1.0},
  {"event_index": 3, "relevance_score": 0.1}
]

❌ WRONG: {"event_index": 1, "relevance_score": 0.8}, {"event_index": 2, "relevance_score": 1.0}
✅ CORRECT: [{"event_index": 1, "relevance_score": 0.8}, {"event_index": 2, "relevance_score": 1.0}]

If you output anything other than a JSON array, your response will be rejected.

**CRITICAL OUTPUT FORMAT REQUIREMENT:**
Your final output MUST be a single JSON array containing all relevance evaluations. Each evaluation is a JSON object within this array. The format must be:
```json
[
  {"event_index": 1, "relevance_score": 0.8},
  {"event_index": 2, "relevance_score": 1.0},
  {"event_index": 3, "relevance_score": 0.1}
]
```

DO NOT output multiple separate JSON objects. DO NOT output individual evaluations outside of the array structure.

You will be provided with:
1. The user's original viewpoint/research topic.
2. A numbered list of historical event descriptions.

**IMPORTANT**: This is for constructing comprehensive chronological timelines. Events from ANY time period (early career, recent developments, historical background) are equally valuable if they relate to the topic. Do NOT penalize events based on when they occurred.

Please evaluate the relevance of EACH event on a scale from 0.0 to 1.0, where:
- 1.0 = Highly relevant, directly supports or relates to the viewpoint
- 0.8-0.9 = Very relevant, strongly connected to the viewpoint
- 0.6-0.7 = Moderately relevant, some clear connection exists
- 0.4-0.5 = Somewhat relevant, tangential connection
- 0.2-0.3 = Minimally relevant, very weak connection
- 0.0-0.1 = Not relevant, no meaningful connection

Consider the following factors when evaluating relevance:
1. **Direct topical connection**: Does the event directly relate to the main subject or theme?
2. **Entity overlap**: Do the people, places, or organizations involved connect to the viewpoint?
3. **Causal or contextual relationship**: Does the event provide important context, causes, or consequences?
4. **Thematic coherence**: Does the event support or illustrate key themes in the viewpoint?
5. **Biographical/chronological value**: For person-focused topics, does the event contribute to understanding their life story, career development, or character?

**Key Principle**: All time periods are equally important. Early career events, foundational experiences, and historical background are just as valuable as recent developments for building comprehensive timelines.

Respond with a JSON array where each object contains the 'event_index' and its corresponding 'relevance_score'.
The 'event_index' must match the index from the input list (1-based indexing).

Example:
Viewpoint: "Steve Jobs"
Events:
1. Steve Jobs worked at Atari as a technician in 1974
2. Steve Jobs co-founded Apple Computer Company in 1976
3. Random person started a tech company

Expected output:
[
  {"event_index": 1, "relevance_score": 0.8},
  {"event_index": 2, "relevance_score": 1.0},
  {"event_index": 3, "relevance_score": 0.1}
]

Provide ONLY the JSON array in your response. Do not include any explanations or additional text.
"""
