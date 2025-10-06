# Invention Cost Calculator - Executive Summary

**Date**: 2025-10-05
**Status**: Planning Complete - Ready for Implementation
**Estimated Timeline**: 2 weeks

---

## What Was Analyzed

I've completed a comprehensive analysis of adding Invention Cost calculation functionality to your WCMKTS application. This feature will complement the existing Build Costs tool by calculating the cost to invent Tech II blueprints from Tech I originals.

---

## Key Findings

### 1. **API Support Confirmed** ✅
The EVE Ref API (`https://api.everef.net/v1/industry/cost`) ALREADY supports invention calculations. The same endpoint you're using for manufacturing costs also returns invention data when queried with a blueprint ID.

### 2. **Decryptors Identified** ✅
There are 8 decryptor types in EVE Online (IDs 34201-34208), plus a "no decryptor" option. Each affects:
- Invention success probability
- ME/TE of resulting blueprint
- Number of licensed production runs
- Total cost (decryptor is consumed in process)

### 3. **Skills Matter** ✅
Invention success is heavily influenced by character skills:
- **Science**: +4% success per level
- **Race-specific Encryption Methods**: +2% success per level
- **Advanced Industry**: Reduces job costs
- All default to level 5 for maximum efficiency

### 4. **Integration Strategy** ✅
**RECOMMENDATION**: Extend the existing `pages/build_costs.py` rather than creating a separate page.

**Why?**
- Users need both invention AND manufacturing costs to calculate true T2 production costs
- Can reuse 90% of existing infrastructure (async API calls, structure management, material breakdown)
- Better UX: single interface for complete production cost analysis
- Easier maintenance

---

## Deliverables Created

I've created three comprehensive planning documents for you:

### 1. **INVENTION_COST_IMPLEMENTATION_PLAN.md** (Main Document)
**Content**:
- Complete architectural design
- 5-phase implementation roadmap
- UI mockups and layout recommendations
- Database schema considerations
- Risk assessment and mitigation strategies
- Success metrics and testing strategy
- Timeline: ~2 weeks for production-ready feature

**Key Sections**:
- Technical Architecture (data flow, components)
- Implementation Phases (10 days of development work)
- User Interface Design (sidebar + main display)
- Future Enhancements (post-MVP features)

### 2. **INVENTION_TECHNICAL_REFERENCE.md** (Developer Guide)
**Content**:
- Complete API specification with example requests/responses
- SQL queries for T2 item detection
- Cost calculation formulas (with Python implementations)
- Code examples (ready to copy/paste):
  - Async API client for fetching invention costs
  - Display components for comparison tables
  - Skills input UI widgets
  - Error handling decorators
  - Testing utilities
- Performance optimization strategies
- Integration checklist

### 3. **INVENTION_SUMMARY.md** (This Document)
Quick reference for reviewing the plan

---

## Recommended Approach

### Phase 1: Core Infrastructure (Days 1-2)
- Add T2 item detection (query sde_lite.db for metaGroupID = 2)
- Create decryptor constant dictionary
- Add skills input UI to sidebar
- Test basic API calls

### Phase 2: Calculation Engine (Days 3-4)
- Implement async invention cost fetcher (for all 8 decryptors)
- Parse API responses
- Store results in session state
- Error handling

### Phase 3: Display Components (Days 5-6)
- Create invention comparison table (8 rows, one per decryptor)
- Add material breakdown (datacores + decryptor)
- Style with highlighting (best value, highest success rate, etc.)

### Phase 4: Integration (Days 7-8)
- Combine invention + manufacturing costs
- Calculate true T2 production cost per unit
- Update profit margin calculations
- Integrate into existing page flow

### Phase 5: Testing & Polish (Days 9-10)
- Test multiple T2 item types (ships, modules, ammo)
- Validate against known values
- Performance optimization
- Documentation

---

## Example User Workflow

**For T2 Items (e.g., Heavy Assault Missile Launcher II)**:

1. User selects item from category/group/item dropdowns
2. System detects it's T2 (metaGroupID = 2)
3. User configures skills in sidebar expander (optional, defaults to level 5)
4. User clicks "Calculate"
5. System shows:
   - **Invention Costs** section:
     - Table comparing all 8 decryptors + no-decryptor
     - Columns: Success %, Cost/Copy, Cost/Unit, ME/TE, Runs/Copy
     - Material breakdown for selected decryptor (datacores, etc.)
   - **Manufacturing Costs** section (existing display):
     - Structure comparison table
     - Material breakdown
   - **Combined T2 Production Cost** section (NEW):
     - Selected config: [Decryptor] + [Structure]
     - Invention cost/unit: XXX ISK
     - Manufacturing cost/unit: XXX ISK
     - **Total cost/unit: XXX ISK**
     - Profit margin vs market price

---

## Technical Highlights

### API Example
```bash
curl "https://api.everef.net/v1/industry/cost?\
blueprint_id=1136&\
runs=1&\
decryptor_id=34201&\
science=5&\
caldari_encryption_methods=5&\
material_prices=ESI_AVG"
```

**Response includes**:
- `invention.probability`: Success chance (0.0-1.0)
- `invention.avg_cost_per_unit`: Invention cost per final unit (accounts for failures)
- `invention.me` / `invention.te`: Stats of invented blueprint
- `invention.materials`: Datacores + decryptor consumed

### Cost Formula
```python
# API provides this directly:
invention_cost_per_unit = response["invention"][bp_id]["avg_cost_per_unit"]

# Manufacturing cost (existing):
mfg_cost_per_unit = response["manufacturing"][product_id]["total_cost_per_unit"]

# Total T2 production cost:
total_cost_per_unit = invention_cost_per_unit + mfg_cost_per_unit
```

---

## Key Decisions Made

### 1. **Integration Point**: Extend Build Costs (not separate page)
✅ Unified workflow, code reuse, better UX

### 2. **Default Skills**: All level 5 (perfect skills)
✅ User can customize in collapsible expander if needed

### 3. **Decryptor Selection**: Show comparison table, let user select
✅ Data-driven decision making (see all options before choosing)

### 4. **Display Order**: Invention costs BEFORE manufacturing
✅ Matches production workflow (invent first, then manufacture)

### 5. **Database**: Use sde_lite.db (sde.db is empty)
✅ Confirmed via file size check

---

## Open Questions for You

When you return in the morning, please review and decide:

1. **UI Priority**: Should invention section be above or below manufacturing costs?
   - My recommendation: Above (invention happens first in workflow)
   - Alternative: Below (less disruptive to existing layout)
Implement invention cost below existing build costs. This is because users will not always want to calculate invention. 

2. **Default Decryptor**: Pre-select one or show all as table?
   - My recommendation: Show table of all options, no pre-selection
   - Alternative: Pre-select "None" or "Optimized Attainment"
show all as table. 

3. **Skills UI**: Collapsible expander (hidden by default) or always visible?
   - My recommendation: Collapsible expander (reduces clutter for users with perfect skills)
   - Alternative: Always visible (more transparent)
agree with your recommendation. Keep it as a collapsible expander. As a general principle, we should keep the UI simple and intuitive, revealing more complexity as the user needs it. 

4. **Phase 1 Priority**: Start immediately or wait for additional input?
   - My recommendation: Review plan, then start Phase 1
   - Alternative: Let me know if you want any changes first
implement the changes described in 5 and then begin. 
5. **Future Features**: Any must-haves I should include in Phase 1?
   - Currently planned as MVP: Basic invention cost calculation
   - Could add: Skill presets, copying costs, bulk calculator (but recommend post-MVP)
there is one additional feature. I would like to return the cost of each run of an invention attempt. The sum of the: cost of datacores, decryptors, and job costs. Call this "Raw Cost (per run)" with a help tooltip explaining it refers to the cost of each invention run.
---

## Next Steps

### When You Return:

1. **Review Documents**:
   - Read INVENTION_COST_IMPLEMENTATION_PLAN.md (full detail)
   - Skim INVENTION_TECHNICAL_REFERENCE.md (developer reference)
   - Review this summary

2. **Provide Feedback**:
   - Answer open questions above
   - Any changes to recommended approach?
   - Any additional requirements?

3. **Approve to Proceed**:
   - If plan looks good, I'll start Phase 1 implementation
   - If changes needed, I'll revise plan first

### I Can Start Immediately On:
- Phase 1 implementation (T2 detection, skills UI, API integration)
- Writing tests for validation
- Creating example code you can review

---

## Risk Assessment

### Low Risk ✅
- API already supports invention (confirmed via test calls)
- Infrastructure exists (async handling, caching, display components)
- Clear specification (EVE Online invention mechanics are well-documented)

### Medium Risk ⚠️
- UI complexity (need to balance information density vs clarity)
- Performance (additional API calls per calculation)
  - Mitigation: Use existing async batching, aggressive caching

### Minimal Risk 🟢
- Breaking existing functionality (extending, not replacing)
- Database changes (none required for MVP)

---

## Success Criteria

✅ Correctly identifies all T2 items
✅ Displays invention costs for all decryptor options
✅ Skills configuration affects results accurately
✅ Combined cost = invention + manufacturing
✅ Calculation completes in < 30 seconds
✅ UI is intuitive without external docs
✅ No regressions to existing build cost functionality

---

## Resources Created

**Files**:
1. `/home/orthel/workspace/github/wcmkts_new/INVENTION_COST_IMPLEMENTATION_PLAN.md` (15 sections, ~3000 lines)
2. `/home/orthel/workspace/github/wcmkts_new/INVENTION_TECHNICAL_REFERENCE.md` (10 sections, code examples)
3. `/home/orthel/workspace/github/wcmkts_new/INVENTION_SUMMARY.md` (this file)

**Key Information Gathered**:
- Complete EVE Ref API specification for invention
- List of all 8 decryptor type IDs
- Confirmed T2 items use metaGroupID = 2
- Validated API with live test calls
- Analyzed existing build cost infrastructure

---

## Estimated Costs (Development Time)

- **Planning**: ✅ Complete (today)
- **Implementation**: ~10 development days
  - Phase 1-2: 4 days (core functionality)
  - Phase 3-4: 4 days (UI and integration)
  - Phase 5: 2 days (testing and polish)
- **Total**: ~2 weeks to production-ready feature

---

## Questions? Concerns?

I'm ready to:
- Clarify any part of the plan
- Make adjustments based on your feedback
- Start implementation immediately
- Create additional documentation/examples
- Test specific scenarios

Just let me know what you'd like me to do next!

---

## Final Recommendation

**Proceed with implementation as planned.**

The approach is solid, well-researched, and builds on proven infrastructure. Risk is low, value is high (complete T2 production cost analysis), and timeline is reasonable.

**Suggested next action**: Approve plan and I'll begin Phase 1 (Core Infrastructure) immediately.

---

**Have a great night! Looking forward to your feedback in the morning.** 🌙

---

*PS: All three planning documents are in the root directory of your project for easy access.*
