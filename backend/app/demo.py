from .schemas import JobInput, ProfileInput


def sample_profile(name='Alex Morgan'):
    return ProfileInput(full_name=name, email='demo@example.com', skills=['Python', 'SQL', 'AWS', 'PySpark'],
                        selected_skills=['Python', 'SQL', 'AWS', 'PySpark'],
                        target_titles=['Data Engineer', 'Senior Data Engineer', 'AWS Data Engineer'],
                        experience_years=3, current_ctc_inr=1200000, expected_ctc_inr=1800000).model_dump()


def sample_jobs():
    names = ['Northstar', 'Cloudline', 'Orbit Labs', 'Fieldwork', 'Rivet', 'Juniper Data',
             'Aster Systems', 'Tandem', 'Canvas Labs', 'Beacon', 'Meridian', 'Sundial', 'Acme AI', 'Atlas', 'Outpost', 'Foundry']
    jobs = []
    for i, company in enumerate(names):
        row = JobInput(external_id=f'demo-{i}', source='demo', title='Data Engineer', company=company,
                       url=f'https://example.com/jobs/demo-{i}', description='Build reliable data pipelines using Python, SQL, AWS and PySpark. Collaborate with the analytics team.',
                       work_mode='hybrid', location='Pune', latitude=18.52, longitude=73.85,
                       minimum_experience=2, salary_max_inr=2400000,
                       required_skills=['Python', 'SQL']).model_dump()
        if i == 12:
            row['title'] = 'Machine Learning Engineer'
        if i == 13:
            row['description'] = 'Build reports using SQL and Python.'
        if i == 14:
            row.update(location='Bengaluru', latitude=12.97, longitude=77.59)
        if i == 15:
            row['minimum_experience'] = 8
        jobs.append(row)
    return jobs


def sample_pdf():
    """Create a small, valid text PDF using pypdf's own PDF object model."""
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=612,height=792)
    font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),
                             NameObject('/Subtype'):NameObject('/Type1'),
                             NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    content = DecodedStreamObject()
    content.set_data(b'BT /F1 12 Tf 60 730 Td (Alex Morgan) Tj 0 -20 Td (Data Engineer) Tj 0 -20 Td (Python, SQL, AWS, PySpark) Tj 0 -20 Td (3 years of data engineering experience.) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(content)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()
