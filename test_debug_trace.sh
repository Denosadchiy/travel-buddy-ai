#!/bin/bash

# Test script for debug trace mode
# Usage: ./test_debug_trace.sh <trip_id>

TRIP_ID=${1:-"18e1a3ff-0093-486d-b5cf-380fbad7284a"}
BASE_URL="http://localhost:8000/api/trips"

echo "=========================================="
echo "Testing Fast Draft Debug Trace Mode"
echo "=========================================="
echo ""
echo "Trip ID: $TRIP_ID"
echo ""

# Test 1: Normal request (no debug)
echo "Test 1: Normal request (debug=0)"
echo "------------------------------------------"
curl -s -X POST "${BASE_URL}/${TRIP_ID}/fast-draft?debug=0" \
  -H "Content-Type: application/json" | jq -c 'keys | sort'
echo ""
echo ""

# Test 2: Debug request (with trace)
echo "Test 2: Debug request (debug=1)"
echo "------------------------------------------"
curl -s -X POST "${BASE_URL}/${TRIP_ID}/fast-draft?debug=1" \
  -H "Content-Type: application/json" | jq '.route_trace | {
    trip_id,
    city,
    total_days,
    pace,
    budget,
    generator_input: (.generator_input != null),
    block_traces_count: (.block_traces | length),
    sample_block: (.block_traces[0] | {
      day_number,
      block_index,
      block_type,
      provider_calls: (.provider_calls | length),
      provider_sample: (.provider_calls[0] | {
        provider_name,
        candidates_returned,
        latency_ms,
        status,
        sample_count: (.sample_candidates | length)
      }),
      filter_rules: (.filter_rules_applied | length),
      ranking: (.ranking_trace | {
        total_candidates,
        top_count: (.top_candidates | length),
        avg_score,
        max_score
      }),
      selection: {
        selected_poi_name,
        alternatives_count: (.selection_alternatives | length)
      }
    })
  }'
echo ""
echo ""

# Test 3: Full generator_input details
echo "Test 3: Generator Input Params (debug=1)"
echo "------------------------------------------"
curl -s -X POST "${BASE_URL}/${TRIP_ID}/fast-draft?debug=1" \
  -H "Content-Type: application/json" | jq '.route_trace.generator_input | {
    trip_id,
    city_name,
    coordinates: {
      lat: .city_center_lat,
      lon: .city_center_lon
    },
    dates: {
      start: .start_date,
      end: .end_date,
      total_days
    },
    preferences: {
      pace,
      budget,
      interests,
      num_travelers
    },
    search_params: {
      max_radius_km,
      poi_fetch_limit,
      providers_enabled
    },
    scoring_weights: {
      category_match_weight,
      tag_overlap_weight,
      budget_alignment_bonus
    }
  }'
echo ""
echo ""

# Test 4: Sample provider call details
echo "Test 4: Sample Provider Call Details"
echo "------------------------------------------"
curl -s -X POST "${BASE_URL}/${TRIP_ID}/fast-draft?debug=1" \
  -H "Content-Type: application/json" | jq '.route_trace.block_traces[0].provider_calls[0] | {
    provider_name,
    request_params,
    candidates_returned,
    latency_ms,
    status,
    sample_candidates: (.sample_candidates | map({
      poi_name,
      category,
      rating,
      tags
    }))
  }'
echo ""
echo ""

# Test 5: Filter rules and dropped examples
echo "Test 5: Filter Rules Applied"
echo "------------------------------------------"
curl -s -X POST "${BASE_URL}/${TRIP_ID}/fast-draft?debug=1" \
  -H "Content-Type: application/json" | jq '.route_trace.block_traces[0].filter_rules_applied | map({
    rule_name,
    dropped_count,
    examples: (.examples_dropped | map(.poi_name))
  })'
echo ""
echo ""

# Test 6: Ranking breakdown
echo "Test 6: Ranking Score Breakdown"
echo "------------------------------------------"
curl -s -X POST "${BASE_URL}/${TRIP_ID}/fast-draft?debug=1" \
  -H "Content-Type: application/json" | jq '.route_trace.block_traces[0].ranking_trace.top_candidates | map({
    poi_name,
    total_score,
    factors,
    explanation
  })'
echo ""
echo ""

# Test 7: Selection alternatives
echo "Test 7: Selection Alternatives"
echo "------------------------------------------"
curl -s -X POST "${BASE_URL}/${TRIP_ID}/fast-draft?debug=1" \
  -H "Content-Type: application/json" | jq '.route_trace.block_traces[0] | {
    selected: .selected_poi_name,
    alternatives: (.selection_alternatives | map({
      rank,
      poi_name,
      score,
      reason_not_selected
    }))
  }'
echo ""
echo ""

echo "=========================================="
echo "Tests Complete!"
echo "=========================================="
