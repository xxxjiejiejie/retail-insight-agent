from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.api.schemas import (
    PolicyDetailResponse,
    PolicyMetadataItem,
    PolicyMetadataResponse,
    PolicySectionResponse,
    SchemaColumnResponse,
    SchemaMetadataResponse,
    SchemaTableResponse,
)
from app.core.config import get_settings
from app.core.errors import DatabaseQueryError
from app.database.schema import load_schema_catalog
from app.rag.loader import (
    chunk_policy_document,
    load_policy_documents,
    policy_document_sections,
)

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("/schema", response_model=SchemaMetadataResponse)
async def get_schema_metadata() -> SchemaMetadataResponse:
    try:
        catalog = await load_schema_catalog()
    except DatabaseQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="经营数据库元数据暂时不可用。",
        ) from exc
    return SchemaMetadataResponse(
        tables=[
            SchemaTableResponse(
                name=table_name,
                columns=[
                    SchemaColumnResponse(
                        name=column.name,
                        type=column.type,
                        nullable=column.nullable,
                    )
                    for column in catalog.details.get(table_name, [])
                ],
            )
            for table_name in sorted(catalog.tables)
        ]
    )


@router.get("/policies", response_model=PolicyMetadataResponse)
async def get_policy_metadata() -> PolicyMetadataResponse:
    directory = Path(get_settings().policy_documents_path)
    try:
        documents = load_policy_documents(directory)
        items: list[PolicyMetadataItem] = []
        for document in documents:
            chunks = chunk_policy_document(document)
            items.append(
                PolicyMetadataItem(
                    document_id=document.document_id,
                    title=document.title,
                    version=document.version,
                    effective_date=document.effective_date,
                    source=document.source,
                    section_count=len({chunk.section for chunk in chunks}),
                    chunk_count=len(chunks),
                )
            )
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="制度知识库元数据暂时不可用。",
        ) from exc
    return PolicyMetadataResponse(documents=items)


@router.get("/policies/{document_id}", response_model=PolicyDetailResponse)
async def get_policy_detail(document_id: str) -> PolicyDetailResponse:
    directory = Path(get_settings().policy_documents_path)
    try:
        documents = load_policy_documents(directory)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="制度知识库暂时不可用。",
        ) from exc

    document = next(
        (item for item in documents if item.document_id == document_id),
        None,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到制度文档。",
        )

    return PolicyDetailResponse(
        document_id=document.document_id,
        title=document.title,
        version=document.version,
        effective_date=document.effective_date,
        source=document.source,
        sections=[
            PolicySectionResponse(
                title=section.title,
                content=section.content,
                page=section.page,
            )
            for section in policy_document_sections(document)
        ],
    )
