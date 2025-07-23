This will detail a number of formatting changes that will allow us to use the transformation specification immediately after curation without needing a reformatting and normalizing step.

I want to be clear that I may have given the impression that a lot of these mistakes were correct and that I know my guidance was lacking. These are changes we need to make the initial transformation specifications we create ready to go directly into LinkML-Map without needing any cleanup that I've been doing before.


## Class Derivations
All `- class_derivations:` tags should have a `- ` in front of them like this:
```
- class_derivations:
    MeasurementObservation:
      populated_from: pht001450
        value_quantity:
          object_derivations:
          - class_derivations:
              Quantity:
                populated_from: pht001450
                slot_derivations:
                  value_decimal:
                    expr: {phv00098846} * 30.48
                  unit:
                    expr: "cm"
```


## Expressions
The most difficult problems that I ran into all had to do with issues in the `expr:` tag. I have fixed some of these by implementing features in LinkML-Map and others just need a simple correction in formatting. Expressions are difficult to use and understand so I suggest we try to avoid them whenever possible. We should generally use `value:`, `value_mappings:`, and `unit_conversion:` for most of the instances we've used `expr:` in the past. The only time we should use an `expr:` is when we are doing something with multiple columns or something complex.
### Value for Constants
We previously used the `expr:` tag to supply constant values. Now that I have implemented the `value:` tag this is much easier.

**Replace `expr:`**
```
expr: "'OMOP:123456'"
```
**With `value:`**
```
value: OMOP:123456
```
No quoting is necessary, but single quotes are fine. We also can't have comments in these lines or they will be added to the value in the slot.

### Value Mappings
If you are planning to use a `expr: case(...)` statement for a field that only uses a single phv# it should probably be a `value_mappings:` tag instead.
So if you should do something like this:
```
populated_by: phv00099556
  value_mappings:
      '1': 'RxCUI:1191'
      '2', 'RxCUI:1192'
```
I would prefer that we do single double-quotes around both sides of the `value_mappings:` key, value pairs. Technically we only need the quoting on the left hand side but certain symbols ( i.e. > ) require the whole string to be quoted. I think it is simpler just to quote both sides all the time. Either quote style is fine but I think it is easiest if we remain consistent.

And not do this:
```

expr: 'case(
        (phv00099556 == 1, "RxCUI:1191"),
        (phv00099556 == 2, "RxCUI:1192")
      )'
```

### Unit Conversion
We recently implemented the ability to define `unit_conversion:` in LinkML-Map. This means that we should now do our unit conversions like this:
```
value_decimal:
  populated_from: phv00283311
  unit_conversion:
    source_unit: "[in_i]"
    target_unit: "cm"
```
and we no longer need to use the `expr:` tag like we used to:
```
value_decimal:
  expr: '{phv00283311} * 2.54'
```
This may seem more complicated but it should be less error prone and it is more declarative so it's easier to tell what is being done and why.
### Case Statements
It is really easy to get case statements wrong. **Whenever possible** we should avoid case statements in `expr:` tags. It is generally preferable to use value_mappings and I'd like to start using `unit_conversion:` if that isn't too difficult. When we do use `case` statements in expressions, here are some of the common problems I encountered.
#### Indentation and Line Breaks
Case statements can be indented with line breaks for readability but they don't need to be. Both of these `expr: case(...)` statements are valid. 

```
expr: case((phv00099556 == 1, "RxCUI:1191"), (phv00099557 == 1, "RxCUI:1191"))
```
When you break over multiple lines you nee to quote the expression with single quotes like this.
```
expr: 'case(
        (phv00099556 == 1, "RxCUI:1191"),
        (phv00099557 == 1, "RxCUI:1191")
      )'
```
When I'm figuring out the problems with a case statement I always break it over multiple lines and indent to understand the flow. When using single quotes over the whole expression you need to make sure that internal quoting only uses double quotes.
#### Extraneous Internal Case
When we have a case statement it should look like this:
```
expr: 'case(
        (phv00099556 == 1, "RxCUI:1191"),
        (phv00099557 == 1, "RxCUI:1191")
      )'
```
If _all_ of the phv#'s in the case statement are the same phv and we don't have any weird logic going on, it should be a `value_mappings:` instead. Sometimes, I've seen internal case statements when the don't make sense.

Don't do this:
```
expr: 'case(
        (phv00099556 == 1, "RxCUI:1191"),
        case(phv00099557 == 1, "RxCUI:1191")
      )'
```
#### End Case Statement
The last case statement needs to be structured just like all the others as `(test = 'val', "")`. I've seen a lot that are a single value, like `None`, or '`''RxCUI:1191'''`.
The last case statement also needs to be a complete statement so we should have this:
```
expr: 'case(
        (phv00099556 == 1, "RxCUI:1191"),
        (True, "RxCUI:1191")
      )'
```
So **not** this:
```
expr: 'case(
        (phv00099556 == 1, "RxCUI:1191"),
        "RxCUI:1191"
      )'
```
And **not** this:
```
expr: 'case(
        (phv00099556 == 1, "RxCUI:1191"),
        None
      )'
```
If you have a case statement where there is not a default value and instead you want the field to be empty if none of the statements are `True`, you don't need to declare that. If none of the statements match the field will be empty by default.


## Quotations
Our use of `expr:` tags as a work-around for the missing `value:` tag resulted in some weird quoting that looked like this. For quoting going forward try to only use a single double quote, like this.
```
"RxCUI:1191"
```
We could also use single quotes but I would like to reserve those for when we need to quote expressions across multiple lines allowing us to use double-quotes internally. 

We ended up with some weird quoting from the workaround that we don't want it looked like this:
```
'''RxCUI:1191'''
'"RxCUI:1191"'
```
We no longer need to quote anything with the triple quotes and I'm working to remove this from the transformation specs we currently have. In some cases it won't cause any problems and in others it results in weird quoting being added to the value.

### Tricky Quotations
In certain cases, we may need to quote a string that contains quotes. The generally rule is to use the other type of quote to contain the string that requires quoting. Here is an example
```
expr: "case: (({phv123456} == 1, 'This contains a " quotation') )"
```
In the above `expr:`, I reversed the quoting around the `case` and the string so that I could contain the double quote that is within the string. If you have things like this just give it a try. If I have a correct a few that are hard to get right that is just fine.
## Format Issues

### Tabs
We can't have tabs anywhere in the document. YAML can't parse them. These are also tricky to spot because, obviously, you can't see whether you've used tabs or spaces. Please make sure any text you are copying and pasting have no tabs in them. It is safe to use text from any of my '-ingest' files. I will have removed all tabs from those files (or LinkML-Map won't work).
### Skipping `populated_from:`
This is an error that I almost always have to correct manually so it's important to me that we stop seeing it. You can't list the phv# for a slot on that slot directly, it must be in a `populated_from:` tag. So we need to have this:
```
ethnicity:
  populated_from: phv00105652
```
And we can't ever have this:
```
ethnicity: phv00105652
```
I think this is mostly corrected now but I just wanted to make sure we have it corrected going forward.
### Don't use in-line comments
```
value: OMOP:123456 # OMOP Meaning
```
The above will make the value of the slot literally ''OMOP:123456 # OMOP Meaning". We don't want this. If you need comments in the file you can do whole line comments like this:
```
# OMOP Meaning
value: OMOP:123456
```
There are places where we can have the inline comments but I think it's too difficult to explain where it is okay and where it isn't.

## Quantity
The tag `value_quantity:` should look like this.
```
        value_quantity:
          object_derivations:
          - class_derivations:
              Quantity:
                populated_from: pht001004
                slot_derivations:
                  value_decimal:
                    populated_from: phv00078866
                  unit:
                    expr: '''{#}/wk'''
```
value_quantity.unit should just be the `unit:` tag within this nested `class_derivation:`

## Remove out-of-scope
If we don't have the files for certain tables that we may later get we need to remove those from the transformation spec. Having a `populated_from: phv#` for a file that is missing will cause LinkML-Map to crash. If you want to preserve the information you can comment out the entire `class_derivation:`
```
# - class_derivations:
#     Condition:
#       populated_from: pht001492
#       slot_derivations:
#         associated_participant:
#           populated_from: phv00107443
#         associated_visit:
#           expr: '''CHS YEAR 6'''
#         condition_concept:
#           expr: '''MONDO:0004981''' #atrial fibrillation
#         condition_status:
#           populated_from: phv00107949
#           value_mappings:
#             '1': '''ABSENT'''
#             '2': '''PRESENT'''
#             '3': '''PRESENT'''
#         condition_provenance:
#           expr: '''PATIENT_SELF-REPORTED_CONDITION'''
#         relationship_to_participant:
#           expr: '''ONESELF'''
```
