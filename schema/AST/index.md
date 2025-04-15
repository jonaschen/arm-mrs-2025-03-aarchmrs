<!-- Copyright (c) 2010-2025 Arm Limited or its affiliates. All rights reserved. -->
<!-- This document is Non-confidential and licensed under the BSD 3-clause license. -->
# Abstract Syntax Tree

Expressions describing conditionality or constraints of the AARCHMRS data are expressed using an Abstract Syntax Tree (AST) format.
This format mainly stems from two base AST nodes:

## $(AST.BinaryOp)

To represent expressions such as `A --> B` or `A == B` etc. we  use $(AST.BinaryOp).

## $(AST.UnaryOp)
To represent expressions such as `NOT x`, `-2` or `!(A)` we use  $(AST.UnaryOp).

The rest of the AST models are used within these contexts.

!!! note

    The `AST` in AARCHMRS is designed to closely match the Arm ASL language, it does not represent the
    full possible scope of ASL, it is limited to concepts needed by the current schema.
