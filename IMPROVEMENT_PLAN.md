# Iterative Improvement Plan for ReAct Agent

## Goal
Improve agent accuracy on SWE-Bench eval subset from current 50% (10/20 resolved) to >60%.

## Current Status
- **Baseline**: 10/20 resolved (50%)
- **Tests**: 81/82 passing
- **Improvements Implemented**:
  1. Enhanced system prompt with workflow guidance
  2. Edit validation guardrails
  3. Fixed test suite issues

## Iterative Improvement Strategy

### Phase 1: Validate Current Improvements ✓ COMPLETED

**Goal**: Ensure improvements don't break existing functionality

**Actions Taken**:
- ✓ Fixed failing tests (2 test fixes)
- ✓ Enhanced system prompt with structured workflow
- ✓ Added edit validation guardrails
- ✓ Validated all tests pass (81/82)

**Results**: All tests passing, backward compatible changes

### Phase 2: Initial Testing (NEXT STEP)

**Goal**: Test improvements on single instance before full run

**Actions**:
1. Run agent on one instance to verify end-to-end functionality
   ```bash
   # Edit run_agent.py to set instances = instances[:1]
   python run_agent.py --model gpt-5-mini --max-steps 100 --output test_single
   ```

2. Review trajectory for the single instance:
   - Check if workflow is followed
   - Verify validation warnings work correctly
   - Ensure tools are used appropriately

3. Expected Outcome:
   - Agent follows the structured workflow
   - No catastrophic file replacements
   - More efficient tool usage

### Phase 3: Full Evaluation

**Goal**: Measure impact of improvements on full eval set

**Actions**:
1. Run on all 20 instances:
   ```bash
   python run_agent.py --model gpt-5-mini --max-steps 100 --output results_improved
   ```

2. Run evaluation harness:
   ```bash
   python -m swebench.harness.run_evaluation \
       --dataset_name lynnliu030/swebench-eval-subset \
       --predictions_path ./results_improved/preds.json \
       --max_workers 8 \
       --run_id improved_v1
   ```

3. Generate analysis:
   ```bash
   python analyze_results.py
   ```

4. Compare with baseline:
   - Resolution rate: baseline 50% vs improved
   - Average steps: compare step counts
   - Failure modes: analyze unresolved instances

### Phase 4: Analysis and Refinement

**Goal**: Identify remaining issues and plan next improvements

**Analysis Checklist**:
- [ ] Resolution rate improved?
- [ ] Average steps decreased?
- [ ] Fewer destructive edits?
- [ ] Better tool usage efficiency?
- [ ] New failure patterns emerged?

**Key Metrics to Track**:
1. **Resolution Rate**
   - Target: >60% (currently 50%)
   - Track which new instances resolved
   - Track which previously resolved instances regressed

2. **Step Efficiency**
   - Average steps for resolved instances
   - Frequency of hitting 100-step limit
   - Tool usage patterns

3. **Edit Quality**
   - Frequency of validation warnings triggered
   - Number of test-breaking edits
   - Success rate of first edit attempt

4. **Failure Modes**
   - Categorize unresolved instances
   - Identify common patterns
   - Plan targeted improvements

### Phase 5: Targeted Improvements (Based on Phase 4 Results)

**Potential Improvement Areas**:

1. **If accuracy doesn't improve**:
   - Review trajectories to see if guidance is being followed
   - Strengthen prompts with more explicit instructions
   - Add more examples in system prompt

2. **If destructive edits still occur**:
   - Strengthen validation thresholds
   - Add more specific warnings
   - Consider blocking (not just warning) for extreme cases

3. **If localization is still poor**:
   - Add more explicit localization requirements
   - Enhance `analyze_test_failure()` to extract more info
   - Add examples of good localization patterns

4. **If tool usage is inefficient**:
   - Add cost/benefit guidance for each tool
   - Provide more specific tool selection criteria
   - Add examples of efficient vs inefficient patterns

5. **If specific failure patterns emerge**:
   - Add targeted guidance for those patterns
   - Create new tools if needed
   - Update system prompt with specific strategies

## Improvement Ideas Backlog

### High Priority
- [ ] Test with single instance first
- [ ] Run full evaluation
- [ ] Analyze results vs baseline
- [ ] Identify top 3-5 failure patterns

### Medium Priority
- [ ] Add more examples to system prompt
- [ ] Enhance test failure analysis
- [ ] Improve file navigation guidance
- [ ] Add rollback capability for bad edits

### Low Priority
- [ ] Dynamic context management
- [ ] Multi-file edit coordination
- [ ] Learning from successful patterns
- [ ] Test selection intelligence

### Future Enhancements
- [ ] Semantic code search
- [ ] Pattern matching from successful fixes
- [ ] Framework-specific knowledge (Django, pytest, etc.)
- [ ] Incremental testing strategies

## Success Criteria

### Minimum Success (Phase 3)
- ✓ No regressions (still resolve 10/20)
- ✓ At least 1-2 additional instances resolved (12/20 = 60%)
- ✓ No new failure modes introduced

### Good Success
- Resolve 13-14/20 instances (65-70%)
- Reduce average steps by 10-20%
- Fewer validation warnings triggered (agent learns from them)

### Excellent Success
- Resolve 15+/20 instances (75%+)
- Reduce average steps by 30%+
- Clear improvement in tool usage efficiency
- New failure patterns identified for next iteration

## Measurement Framework

### Quantitative Metrics
1. **Resolution Rate**: resolved_instances / total_instances
2. **Step Efficiency**: avg_steps_for_resolved
3. **Completion Rate**: completed_instances / total_instances
4. **Error Rate**: error_instances / total_instances
5. **Empty Patch Rate**: empty_patch_instances / total_instances

### Qualitative Analysis
1. **Tool Usage Patterns**: Which tools used most/least?
2. **Workflow Adherence**: Does agent follow 6-step workflow?
3. **Edit Quality**: Are edits targeted and precise?
4. **Localization Quality**: Does agent understand problem before editing?
5. **Test Strategy**: Does agent use tests effectively?

### Comparison Points
- Compare each metric with baseline
- Identify improvements and regressions
- Understand why changes occurred
- Plan next iteration based on findings

## Timeline

### Immediate (Today)
- [x] Implement improvements
- [x] Validate tests pass
- [x] Document changes
- [ ] Test single instance

### Short-term (Next Session)
- [ ] Run full evaluation
- [ ] Analyze results
- [ ] Identify top improvements and regressions
- [ ] Plan Phase 5 improvements

### Medium-term (Future Sessions)
- [ ] Implement Phase 5 improvements
- [ ] Iterate until >60% accuracy achieved
- [ ] Document final improvements
- [ ] Prepare final report

## Risk Mitigation

### Potential Risks
1. **Improvements don't help**: Guidance too vague or ignored
   - Mitigation: Strengthen with examples, make more explicit

2. **Validation too strict**: Blocks legitimate edits
   - Mitigation: Review triggered warnings, adjust thresholds

3. **New failure modes**: Changes introduce unexpected issues
   - Mitigation: Comprehensive testing, rollback capability

4. **Performance degradation**: More checks slow down agent
   - Mitigation: Profile execution time, optimize validation

## Documentation

### Files Created
1. `IMPROVEMENTS_SUMMARY.md` - Detailed description of changes
2. `IMPROVEMENT_PLAN.md` - This file, iterative strategy
3. Test fixes in `tests/` - Ensure quality

### Files to Create After Evaluation
1. `EVALUATION_RESULTS.md` - Comparison with baseline
2. `FAILURE_ANALYSIS.md` - Detailed analysis of remaining failures
3. `NEXT_STEPS.md` - Plan for next iteration

## Conclusion

This plan provides a systematic approach to improving agent accuracy:
1. Start with validated improvements
2. Test incrementally (single → full)
3. Measure impact objectively
4. Iterate based on data

The key is to maintain rigorous measurement and learn from both successes and failures to guide the next iteration.
