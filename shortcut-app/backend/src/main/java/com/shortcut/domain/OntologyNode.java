package com.shortcut.domain;

import com.fasterxml.jackson.databind.JsonNode;

public record OntologyNode(String nodeId, String type, String label, JsonNode props) {
}
