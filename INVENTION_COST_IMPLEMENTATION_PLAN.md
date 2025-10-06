# Invention Cost Calculator - Implementation Plan

## Executive Summary

This document outlines the recommended approach for adding Invention Cost calculation capabilities to the Winter Coalition Market Stats (WCMKTS) application. The implementation will extend the existing Build Cost infrastructure to provide comprehensive invention cost analysis for Tech II items, including support for different decryptor types and skill configurations.

---

## 1. Background & Context

### Current State
- **Existing Tool**: Build Cost calculator (pages/build_costs.py) successfully calculates manufacturing costs using the EVE Ref API
- **API Endpoint**: `https://api.everef.net/v1/industry/cost` already supports invention calculations
- **Infrastructure**: Async/sync request handling, structure management, and material cost breakdown are already implemented
- **Database**: build_cost.db contains structures, rigs, and industry indices

### Requirements
- Calculate invention costs for Tech II items (MetaGroupID = 2)
- Display costs for each decryptor type in a comparison table
- Allow users to configure skill levels
- Integrate invention costs into overall build cost calculations
- Maintain consistency with existing Build Cost tool UX

---

## 2. Technical Architecture

### 2.1 Recommended Approach: Extend Build Costs Page

**Recommendation**: Add invention cost functionality to the existing `pages/build_costs.py` rather than creating a separate page.

**Rationale**:
1. **Unified Workflow**: Manufacturers need both invention and manufacturing costs together to calculate true production costs
2. **Code Reuse**: Can leverage existing API infrastructure, async handling, structure selection, and material breakdown
3. **User Experience**: Single interface for complete T2 production cost analysis
4. **Maintainability**: Reduces code duplication and keeps related functionality together

### 2.2 Data Flow Architecture

```
User Input (Item Selection + Skills)
    ↓
Detect if T2 Item (metaGroupID == 2)
    ↓
API Request Construction
    ├─→ Manufacturing Cost (existing)
    └─→ Invention Cost (new) - for each decryptor
            ↓
Async Batch Processing
    ↓
Results Display
    ├─→ Manufacturing costs by structure
    ├─→ Invention costs by decryptor (NEW)
    └─→ Combined total cost analysis (NEW)
```

---

## 3. Implementation Components

### 3.1 Decryptor Management

**New Data Structure**:
```python
DECRYPTORS = {
    "None (No Decryptor)": None,
    "Accelerant Decryptor": 34201,
    "Attainment Decryptor": 34202,
    "Augmentation Decryptor": 34203,
    "Parity Decryptor": 34204,
    "Process Decryptor": 34205,
    "Symmetry Decryptor": 34206,
    "Optimized Attainment Decryptor": 34207,
    "Optimized Augmentation Decryptor": 34208,
}
```

**Impact**: Each decryptor affects:
- Invention probability (success chance)
- ME/TE of resulting blueprint copy
- Number of licensed production runs
- Material costs (decryptor itself is consumed)

### 3.2 Skills Configuration Interface

**Required Skill Inputs** (sidebar configuration):

**Science Skills**:
- Science (default: 5)
- Race-specific Encryption Methods (Amarr/Caldari/Gallente/Minmatar/Triglavian/Upwell/Sleeper) (default: 5)

**Industry Skills** (may already exist):
- Advanced Industry (default: 5)
- Industry (default: 5)

**Optional Skills**:
- Research (affects copy time, not invention directly)
- Various race-specific starship engineering skills

**UI Recommendation**: Use `st.expander()` for skill configuration to avoid cluttering the sidebar

### 3.3 Modified JobQuery Dataclass

Extend existing `JobQuery` to include invention parameters:

```python
@dataclass
class JobQuery:
    item: str
    item_id: int
    group_id: int
    runs: int
    me: int
    te: int
    security: str = "NULL_SEC"
    system_cost_bonus: float = 0.0
    material_prices: str = "ESI_AVG"

    # NEW: Invention-specific fields
    calculate_invention: bool = False
    decryptor_id: int | None = None

    # Skills (NEW)
    science: int = 5
    advanced_industry: int = 5
    industry: int = 5
    amarr_encryption: int = 5
    caldari_encryption: int = 5
    gallente_encryption: int = 5
    minmatar_encryption: int = 5
    triglavian_encryption: int = 5
    upwell_encryption: int = 5
    sleeper_encryption: int = 5
```

### 3.4 URL Construction Enhancement

Extend `construct_url()` method to append invention parameters:

```python
def construct_invention_url(self, decryptor_id: int | None = None):
    """Construct URL for invention cost calculation"""
    base_params = [
        f"blueprint_id={self.item_id}",
        f"runs={self.runs}",
        f"science={self.science}",
        f"advanced_industry={self.advanced_industry}",
        f"industry={self.industry}",
        f"amarr_encryption_methods={self.amarr_encryption}",
        f"caldari_encryption_methods={self.caldari_encryption}",
        f"gallente_encryption_methods={self.gallente_encryption}",
        f"minmatar_encryption_methods={self.minmatar_encryption}",
        # ... other skills
        f"material_prices={self.material_prices}"
    ]

    if decryptor_id:
        base_params.append(f"decryptor_id={decryptor_id}")

    url = f"https://api.everef.net/v1/industry/cost?{'&'.join(base_params)}"
    return url
```

### 3.5 API Response Structure

The API returns invention data within the same response as manufacturing:

```json
{
  "manufacturing": { ... },
  "invention": {
    "12619": {  // T2 blueprint type ID
      "product_id": 12619,
      "probability": 0.595,
      "runs_per_copy": 11,
      "expected_copies": 0.595,
      "expected_runs": 6.545,
      "expected_units": 32725.0,
      "me": 4,
      "te": 14,
      "materials": { ... },
      "total_material_cost": 554627.49,
      "total_cost": 554700.49,
      "avg_cost_per_copy": 932269.73,
      "avg_cost_per_run": 84751.79,
      "avg_cost_per_unit": 16.95,
      // ... other fields
    }
  },
  "copying": { ... }
}
```

### 3.6 New Functions Required

#### Detection Function
```python
def is_t2_item(type_id: int) -> bool:
    """Check if item is Tech II (metaGroupID == 2)"""
    # Query sde_lite.db for metaGroupID
    # Return True if metaGroupID == 2
```

#### Invention Cost Calculation
```python
async def get_invention_costs(job: JobQuery) -> dict:
    """
    Get invention costs for all decryptor types
    Returns: {
        "Accelerant Decryptor": {...},
        "Attainment Decryptor": {...},
        ...
    }
    """
    # Similar to get_costs_async but for invention
    # Call API for each decryptor type
    # Parse 'invention' section of response
```

#### Combined Cost Calculator
```python
def calculate_total_t2_cost(
    invention_costs: dict,
    manufacturing_costs: dict,
    selected_decryptor: str,
    selected_structure: str
) -> dict:
    """
    Combine invention and manufacturing costs
    Returns total cost per unit accounting for invention failure rate

    Formula:
    Total Cost = (Invention Cost / Expected Units) + Manufacturing Cost
    """
```

---

## 4. User Interface Design

### 4.1 Sidebar Modifications

**Item Selection** (existing, no changes)
- Category → Group → Item selection
- Runs, ME, TE inputs

**NEW: Skills Configuration Section** (collapsible expander)
```
└─ Skills Configuration (Expander)
    ├─ Science: [slider 0-5, default 5]
    ├─ Advanced Industry: [slider 0-5, default 5]
    └─ Encryption Methods (Expander)
        ├─ Amarr: [slider 0-5, default 5]
        ├─ Caldari: [slider 0-5, default 5]
        ├─ Gallente: [slider 0-5, default 5]
        └─ Minmatar: [slider 0-5, default 5]
```

**Material Price Source** (existing, no changes)

**Calculate Button** (existing, no changes)

### 4.2 Main Display Area

**For T1/Non-Invention Items**: Display as currently implemented

**For T2 Items**: Add new section BEFORE manufacturing costs

```
┌─────────────────────────────────────────────────────┐
│  [Item Image]  Item Name (T2)                       │
├─────────────────────────────────────────────────────┤
│  INVENTION COSTS                                    │
│  ┌───────────────────────────────────────────────┐ │
│  │ Decryptor Comparison Table                    │ │
│  │ Columns:                                       │ │
│  │  - Decryptor Name                             │ │
│  │  - Success Chance (%)                         │ │
│  │  - Avg Cost/Copy                              │ │
│  │  - Avg Cost/Run                               │ │
│  │  - Avg Cost/Unit                              │ │
│  │  - ME/TE Result                               │ │
│  │  - Runs per Copy                              │ │
│  │  - Total Material Cost                        │ │
│  └───────────────────────────────────────────────┘ │
│                                                     │
│  Material Breakdown (for selected decryptor)       │
│  - Datacores, Decryptor, etc.                      │
├─────────────────────────────────────────────────────┤
│  MANUFACTURING COSTS (existing display)             │
│  - Structure comparison table                       │
│  - Material breakdown                               │
├─────────────────────────────────────────────────────┤
│  COMBINED T2 PRODUCTION COST (NEW)                  │
│  Selected Config: [Decryptor] + [Structure]        │
│  - Invention cost/unit: XXX ISK                     │
│  - Manufacturing cost/unit: XXX ISK                 │
│  - Total cost/unit: XXX ISK                         │
│  - Profit margin vs market: XX%                     │
└─────────────────────────────────────────────────────┘
```

---

## 5. Implementation Phases

### Phase 1: Core Invention Infrastructure (Days 1-2)
**Tasks**:
1. Add T2 detection function (query metaGroupID from SDE)
2. Create DECRYPTORS constant dictionary
3. Extend JobQuery dataclass with invention fields
4. Add skill input UI to sidebar (expander)
5. Create `construct_invention_url()` method
6. Test API calls for invention data

**Deliverable**: Ability to detect T2 items and construct valid invention API requests

### Phase 2: Invention Cost Calculation (Days 3-4)
**Tasks**:
1. Implement `get_invention_costs_async()` function
2. Add response parsing for invention data structure
3. Handle error cases (no invention data, API failures)
4. Create invention results storage in session state
5. Test with various T2 items and decryptors

**Deliverable**: Backend system that calculates invention costs for all decryptors

### Phase 3: UI Display Components (Days 5-6)
**Tasks**:
1. Create invention costs comparison table
2. Add material breakdown for selected decryptor
3. Style table with highlighting (lowest cost, best probability, etc.)
4. Add tooltips and help text
5. Implement decryptor selection mechanism

**Deliverable**: Complete invention cost display interface

### Phase 4: Integration & Combined Costs (Days 7-8)
**Tasks**:
1. Implement `calculate_total_t2_cost()` function
2. Create combined cost display section
3. Update profit calculations to include invention costs
4. Integrate with existing manufacturing cost flow
5. Handle caching and recalculation logic

**Deliverable**: Unified T2 production cost calculator

### Phase 5: Testing & Polish (Days 9-10)
**Tasks**:
1. Test with various T2 ship classes (frigates, cruisers, battleships)
2. Test with T2 modules, ammunition, drones
3. Verify skill level impacts
4. Performance optimization (caching, async improvements)
5. Error handling and edge cases
6. Documentation updates (CLAUDE.md)

**Deliverable**: Production-ready feature

---

## 6. Database Schema Changes

### 6.1 Optional: Invention Presets Table

Consider adding a table to store common skill configurations:

```sql
CREATE TABLE invention_skill_presets (
    id INTEGER PRIMARY KEY,
    preset_name TEXT NOT NULL,
    science INTEGER DEFAULT 5,
    advanced_industry INTEGER DEFAULT 5,
    industry INTEGER DEFAULT 5,
    amarr_encryption INTEGER DEFAULT 5,
    caldari_encryption INTEGER DEFAULT 5,
    gallente_encryption INTEGER DEFAULT 5,
    minmatar_encryption INTEGER DEFAULT 5,
    triglavian_encryption INTEGER DEFAULT 5,
    upwell_encryption INTEGER DEFAULT 5,
    sleeper_encryption INTEGER DEFAULT 5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Example presets
INSERT INTO invention_skill_presets VALUES
(1, 'Perfect Skills (All 5)', 5, 5, 5, 5, 5, 5, 5, 5, 5, 5),
(2, 'Beginner (All 3)', 3, 3, 3, 3, 3, 3, 3, 3, 3, 3),
(3, 'Alpha Clone Max', 4, 1, 4, 4, 4, 4, 4, 0, 0, 0);
```

**Benefits**:
- Quick skill configuration switching
- Shareable configurations
- Default profiles for new users

**Note**: This is OPTIONAL and can be added in a future enhancement

---

## 7. Code Structure Recommendations

### 7.1 File Organization

**Extend Existing**: `pages/build_costs.py`
- Keep all invention logic in same file for now
- Use helper functions to separate concerns
- Consider extracting to separate module if file exceeds 2000 lines

**Potential Future Refactor**:
```
pages/
  build_costs/
    __init__.py
    main.py              # Main page logic
    manufacturing.py     # Manufacturing cost calculations
    invention.py         # Invention cost calculations (NEW)
    display.py           # UI components
    api_client.py        # API interaction layer
```

### 7.2 Session State Management

**New Session State Variables**:
```python
if "invention_costs" not in st.session_state:
    st.session_state.invention_costs = None
if "selected_decryptor" not in st.session_state:
    st.session_state.selected_decryptor = "None (No Decryptor)"
if "skill_preset" not in st.session_state:
    st.session_state.skill_preset = "Perfect Skills (All 5)"

# Skill levels
if "science_level" not in st.session_state:
    st.session_state.science_level = 5
# ... (repeat for each skill)
```

### 7.3 Caching Strategy

**Invention Costs**: Cache with same TTL as manufacturing (tied to job parameters)
```python
@st.cache_data(ttl=3600)
def get_invention_costs_cached(job_params_hash: str, ...):
    # Implementation
```

**Decryptor Info**: Static data, cache indefinitely
```python
@st.cache_data
def get_decryptor_info() -> dict:
    return DECRYPTORS
```

---

## 8. API Considerations

### 8.1 Rate Limiting

**Current**: Build cost tool makes ~50-200 requests per calculation (one per structure)

**With Invention**: Additional 8-9 requests per calculation (one per decryptor)

**Mitigation**:
1. Use existing async batching (MAX_CONCURRENCY = 6)
2. Consider caching invention results separately from manufacturing
3. Option to calculate invention costs independently (single API call without structure iteration)

### 8.2 Error Handling

**Scenarios to Handle**:
1. Item is not inventable (no T2 version exists)
2. Missing datacore prices in market
3. API returns no invention data
4. Skill validation (ensure 0-5 range)

**Approach**: Graceful degradation - show warning but still display manufacturing costs

---

## 9. Testing Strategy

### 9.1 Test Cases

**Item Types**:
- [ ] T2 Frigate (e.g., Crow - 11176)
- [ ] T2 Cruiser (e.g., Cerberus - 11993)
- [ ] T2 Battleship (e.g., Golem - 28659)
- [ ] T2 Module (e.g., Heavy Assault Missile Launcher II)
- [ ] T2 Ammunition (e.g., Scourge Rage Heavy Assault Missile)
- [ ] T2 Drone (e.g., Valkyrie II)
- [ ] T1 Item (should NOT show invention section)

**Decryptors**:
- [ ] No decryptor (baseline)
- [ ] Each of the 8 decryptor types
- [ ] Verify different ME/TE results
- [ ] Verify different success probabilities

**Skills**:
- [ ] All skills at 5 (maximum efficiency)
- [ ] All skills at 0 (minimum, should fail or show very poor results)
- [ ] Mixed skill levels (realistic player scenario)
- [ ] Verify Science skill impact on probability
- [ ] Verify Encryption Method skill impact (race-specific)

**Edge Cases**:
- [ ] Very high number of runs (10,000+)
- [ ] Items with very expensive datacores
- [ ] Items with missing market data
- [ ] Network failures during API calls

### 9.2 Validation

**Compare Against**:
- EVE Online in-game industry window
- Other established calculators (if available)
- Manual calculations based on known formulas

---

## 10. Documentation Requirements

### 10.1 User-Facing Documentation

**Add to Application Help Text**:
```markdown
## Invention Costs (T2 Items)

For Tech II items, the tool automatically calculates invention costs
in addition to manufacturing costs.

**Decryptors**: Modify invention success chance and blueprint stats
- Choose different decryptors to see cost/benefit tradeoffs
- "No Decryptor" provides baseline comparison

**Skills**: Configure your character skills for accurate calculations
- Science and Advanced Industry affect success rates
- Encryption Methods are race-specific (match item race)
- Default assumes all skills at level 5

**Total Cost**: Invention cost is amortized across expected output units
- Formula: (Avg Invention Cost / Expected Units) + Manufacturing Cost
```

### 10.2 Developer Documentation

**Update CLAUDE.md**:
```markdown
### Invention Cost Calculations

Tech II item production requires invention from T1 blueprints. The tool:

1. Detects T2 items via metaGroupID == 2
2. Calls API with skill parameters for each decryptor type
3. Calculates expected cost per unit based on invention probability
4. Combines with manufacturing cost for total production cost

**Key Files**:
- `pages/build_costs.py`: Main implementation
- API: `https://api.everef.net/v1/industry/cost`

**Testing**:
```bash
# Run invention cost tests
pytest tests/test_invention_costs.py
```
```

### 10.3 Code Comments

**Critical Sections Requiring Documentation**:
1. Invention probability formula explanation
2. Cost amortization calculation
3. Skill impact on success rates
4. Decryptor effect descriptions

---

## 11. Future Enhancements

### 11.1 Short-term (Post-MVP)

1. **Copying Costs**: Include blueprint copying in total cost calculation
2. **Bulk Calculator**: Calculate invention costs for multiple items simultaneously
3. **Skill Presets**: Save/load skill configurations
4. **Export Results**: CSV/Excel export of invention cost comparison
5. **Historical Tracking**: Track decryptor price changes over time

### 11.2 Long-term

1. **Invention Simulator**: Monte Carlo simulation of invention outcomes
2. **Profitability Analysis**: Compare invention profits across multiple T2 items
3. **Datacore Market Integration**: Real-time datacore price updates
4. **Research Calculator**: Calculate time/cost to research original blueprint
5. **T3 Support**: Extend to T3 reverse engineering if API supports it

---

## 12. Risk Assessment & Mitigation

### 12.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API doesn't return invention data for some items | Medium | High | Detect and display warning, show manufacturing only |
| Skill parameters don't affect results as expected | Low | Medium | Validate with known test cases first |
| Performance degradation from additional API calls | Medium | Medium | Use caching aggressively, separate invention calculation |
| Incorrect cost calculations mislead users | Low | Critical | Extensive testing against known values |

### 12.2 User Experience Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| UI becomes too cluttered | High | Medium | Use expanders, collapsible sections |
| Users confused by invention vs manufacturing costs | Medium | High | Clear labeling, tooltips, help text |
| Skill configuration too complex | Medium | Medium | Provide presets, sensible defaults |
| Slow calculation time frustrates users | Low | Medium | Progress indicators, async processing |

---

## 13. Success Metrics

### 13.1 Functional Criteria

- [ ] Correctly identifies all T2 items (100% accuracy)
- [ ] Displays invention costs for all 8 decryptors + no-decryptor option
- [ ] Skill configuration affects calculations correctly
- [ ] Combined cost calculation is mathematically accurate
- [ ] Performance: Complete calculation in < 30 seconds for typical use case

### 13.2 User Experience Criteria

- [ ] UI is intuitive without requiring external documentation
- [ ] No more than 3 clicks to get results
- [ ] Error messages are clear and actionable
- [ ] Mobile-responsive (Streamlit's default responsive design)

### 13.3 Code Quality Criteria

- [ ] No code duplication > 20 lines
- [ ] All functions have docstrings
- [ ] Type hints on all new functions
- [ ] Test coverage > 80% for new code
- [ ] No new linting errors

---

## 14. Open Questions & Decisions Needed

### 14.1 Questions for Stakeholder (You)

1. **UI Layout**: Should invention costs appear above or below manufacturing costs?
   - **Recommendation**: Above, as invention comes first in production workflow
Invention should come afeter build_costs as some users will not want to calculate invention. 

2. **Default Decryptor**: What should be pre-selected?
   - **Recommendation**: "None (No Decryptor)" as baseline, with table showing all options
Agree. None. 

3. **Skill Defaults**: Assume perfect skills (all 5) or prompt user?
   - **Recommendation**: Default to 5, allow customization in expander
Agree. 

4. **Combined Cost Display**: Show as separate section or integrate into existing tables?
   - **Recommendation**: Separate summary section for clarity
Agree. 

5. **Structure Selection for Invention**: Invention facilities can also have bonuses. Include?
   - **Recommendation**: Start simple (ignore structure bonuses for invention), add later if needed
No. Incorporate structure bonuses. Invention bonuses can be identified based on the rig. 

6. **Save User Preferences**: Remember skill settings between sessions?
   - **Recommendation**: Yes, use session_state, consider localStorage in future
use session state for now. once we have a working implementation we can consider options for persisting user preferences. 

### 14.2 Technical Decisions

1. **SDE Database**: Use sde.db or sde_lite.db for metaGroupID lookup?
   - **Note**: sde.db appears empty (0 bytes), use sde_lite.db
confirm. use sde_line. 

2. **Cache Invalidation**: Should skill changes invalidate cache?
   - **Recommendation**: Yes, include skills in cache key
agree. yes. 

3. **Async vs Sync**: Should invention calculations always be async?
   - **Recommendation**: Yes, for consistency with manufacturing
yes. use async. the async functionality has proven sufficiently stable to be the default. 

---

## 15. Conclusion & Next Steps

### Summary

This plan outlines a comprehensive approach to adding invention cost calculations to the WCMKTS application. By extending the existing Build Costs infrastructure rather than creating a separate tool, we can:

1. Provide a unified T2 production cost calculator
2. Maximize code reuse and maintainability
3. Deliver a superior user experience
4. Minimize development time

### Recommended Immediate Actions

1. **Validate Plan**: Review this document and confirm approach
2. **Setup Development Environment**: Ensure all dependencies are current
3. **Create Feature Branch**: `git checkout -b feature/invention-costs`
4. **Begin Phase 1**: Start with T2 detection and API integration
5. **Iterative Testing**: Test each phase before moving to next

### Estimated Timeline

- **MVP (Phases 1-4)**: 8-10 development days
- **Testing & Polish (Phase 5)**: 2-3 days
- **Total**: ~2 weeks for production-ready feature

### Final Notes

This is a living document. As implementation progresses, update this plan with:
- Actual decisions made
- Challenges encountered and solutions
- Performance metrics
- User feedback

---

## Appendix A: Decryptor Reference

| Decryptor Name | Type ID | Probability Modifier | ME Modifier | TE Modifier | Run Modifier |
|----------------|---------|---------------------|-------------|-------------|--------------|
| None | - | +0% | +2 | +4 | +0 |
| Accelerant | 34201 | +20% | +2 | +14 | +1 |
| Attainment | 34202 | +10% | +3 | +4 | +4 |
| Augmentation | 34203 | -40% | +9 | +2 | +2 |
| Parity | 34204 | +50% | +1 | +2 | -2 |
| Process | 34205 | +10% | +3 | +6 | -1 |
| Symmetry | 34206 | +0% | +1 | +8 | +2 |
| Optimized Attainment | 34207 | +90% | +2 | +4 | +3 |
| Optimized Augmentation | 34208 | +0% | +2 | +4 | +9 |

**Note**: These modifiers are BASELINE values. The actual implementation in the API may use different formulas. Always validate against API responses.

---

## Appendix B: Example API Request

```bash
# Example: Calculate invention cost for Scourge Rage Heavy Assault Missile II
# Blueprint ID: 1136 (Scourge Heavy Assault Missile Blueprint)
# With Accelerant Decryptor (34201)
# Perfect skills (all 5)

curl "https://api.everef.net/v1/industry/cost?\
blueprint_id=1136&\
runs=1&\
decryptor_id=34201&\
science=5&\
caldari_encryption_methods=5&\
advanced_industry=5&\
industry=5&\
material_prices=ESI_AVG"
```

**Expected Response**: JSON with `invention`, `manufacturing`, and `copying` sections

---

## Appendix C: Skill Descriptions

| Skill | Effect on Invention | Priority |
|-------|-------------------|----------|
| Science | +4% success chance per level | Critical |
| Advanced Industry | Reduces job cost | High |
| Industry | Reduces manufacturing time/cost | Medium |
| [Race] Encryption Methods | +2% success chance per level (race-specific) | Critical |
| Research | Reduces copying time (not direct invention impact) | Low |

---

**Document Version**: 1.0
**Date**: 2025-10-05
**Author**: Claude Code (Anthropic)
**Status**: Draft for Review

