import os
import glob
import parsedmarc
import json

def parse_dmarc_xml(file_path):
    """Parse a single DMARC XML file from disk and return structured data."""
    try:
        parsed = parsedmarc.parse_report_file(file_path)
        return parsed
    except Exception as e:
        print(f"❌ Error parsing {file_path}: {e}")
        return None

def format_structure(parsed):
    """Format parsedmarc output into a structure suitable for AI input."""
    report_data = parsed.get('report', {})
    
    formatted_records = []
    for record in report_data.get("records", []):
        source = record.get("source", {})
        identifiers = record.get("identifiers", {})
        policy = record.get("policy_evaluated", {})
        auth_results = record.get("auth_results", {})

        formatted_records.append({
            "source_ip": source.get("ip_address"),
            "source_country": source.get("country"),
            "source_domain": source.get("base_domain"),
            "source_name": source.get("name"),
            "source_type": source.get("type"),
            "count": record.get("count"),
            "header_from": identifiers.get("header_from"),
            "envelope_from": identifiers.get("envelope_from"),
            "envelope_to": identifiers.get("envelope_to"),
            "spf_result": policy.get("spf"),
            "dkim_result": policy.get("dkim"),
            "disposition": policy.get("disposition"),
            "spf_auth": auth_results.get("spf", []),
            "dkim_auth": auth_results.get("dkim", []),
            "alignment": record.get("alignment", {})
        })

    return {
        "report_metadata": report_data.get("report_metadata"),
        "policy_published": report_data.get("policy_published"),
        "records": formatted_records
    }

def parse_and_format_all(folder_path):
    """Parse and format all XML files in the given folder."""
    all_formatted = []
    for xml_file in glob.glob(os.path.join(folder_path, "*.xml")):
        parsed = parse_dmarc_xml(xml_file)
        if parsed:
            formatted = format_structure(parsed)
            all_formatted.append(formatted)
    return all_formatted

def parse_and_format_xml(xml_string):
    parsed = parsedmarc.parse_report_file(xml_string)
    return format_structure(parsed)

def main():
    folder_path = "resources/examples" 
    all_reports = parse_and_format_all(folder_path)

    with open("dmarc_ai_input.json", "w", encoding="utf-8") as f:
        json.dump(all_reports, f, indent=2)

    print("✅ Parsed and formatted all reports. Saved to dmarc_ai_input.json.")

if __name__ == "__main__":
    main()
