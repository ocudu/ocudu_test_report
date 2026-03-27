# Features

This folder contains a structured YAML file listing all relevant features for OCUDU.
Most of those features IDs have their origin in the "ATIS Open RAN Minimum Viable Profile V2", their source is 
therefore tagged with "ATIS-MVP".
The list is further enhanced with additional features that are not explicilty mentioned in the ATIS-MVP
but are deemed important by the project. Those features are tagged as "OCUDU defined".

## Note on ATIS-MVP

In the ATIS-MVP some very essential features like `MVP-FUNC-MOB-1` define multiple scenarios in which
the feature shall be tested. 
Take the following example:
```
MVP-FUNC-MOB-1: The Open RAN system specified in Section 4.1 shall support Intra-band mobility within supported FR1 and
FR2 bands for the following scenarios:
a) Intra-RU, Intra-DU, Intra-CU
b) Inter-RU, Intra-DU, Intra-CU
c) Inter-RU, Inter-DU, Intra-CU
d) Inter-RU, Inter-DU, Inter-CU handovers without CU-UP change
e) Inter-RU, Inter-DU, Inter-CU handovers with CU-UP change
```

Those scenarios impact the test design and and cause fundamental differences in the components involved and configuration used.
Therfore they are split into individual IDs. E.g. `MVP-FUNC-MOB-1-a`, `MVP-FUNC-MOB-1-b`, etc.

# Sources

[ATIS MVP Version 2 v8](https://mvp.atis.org/wp-content/uploads/2025/02/ATIS-Open-RAN-Minimum-Viable-Profile-Report-Version-2-v8.pdf)