# LLM Image Analysis with NATS

이미지를 LLM으로 분석하고 결과를 JSON 형태로 NATS에 publish하는 프로젝트입니다.

## 구성

- main.py
- llm_client.py
- nats_publisher.py

## 기능

- 이미지 분석
- JSON 결과 생성
- NATS publish

## 실행 결과

```json
{
  "summary": "도보로 횡단보도를 건너는 여러 명의 사람들이 도시 도로에서 걸어가는 장면입니다. 사람들이 마스크를 착용하고 있으며, 주변에는 차량과 버스도 있습니다. 날씨는 맑아 보이고, 사람들이 다양한 의상과 스타일로 이동 중입니다.",

  "objects": [
    {
      "type": "people",
      "details": [
        {
          "description": "여성 (피어스와 블론드 헤어, 블랙 드레스, 핑크색 가방)",
          "action": "횡단보도를 건너다"
        },
        {
          "description": "여성 (블랙 드레스, 핑크색 마스크, 핑크색 가방)",
          "action": "횡단보도를 건너다"
        },
        {
          "description": "남성 (블랙 티셔츠, 블랙 바지, 마스크)",
          "action": "횡단보도를 건너다"
        },
        {
          "description": "남성 (화이트 티셔츠, 블랙 바지, 마스크)",
          "action": "횡단보도를 건너다"
        },
        {
          "description": "남성 (블랙 티셔츠, 블루색 슬리퍼, 핑크색 가방)",
          "action": "횡단보도를 건너다"
        },
        {
          "description": "여성 (블랙 드레스, 핑크색 마스크, 핑크색 가방)",
          "action": "횡단보도를 건너다"
        }
      ]
    },
    {
      "type": "vehicles",
      "details": [
        {
          "type": "car",
          "description": "백색 SUV 차량, 도로에서 이동 중"
        },
        {
          "type": "bus",
          "description": "노란색 버스, 도로에서 이동 중"
        }
      ]
    },
    {
      "type": "road_feature",
      "details": [
        {
          "type": "crosswalk",
          "description": "흰색 가로등선으로 표시된 횡단보도"
        }
      ]
    }
  ],

  "risk_level": "low",

  "risk_reason": [
    {
      "reason": "모든 횡단보도 이용자들이 안전하게 횡단보도를 건너고 있으며, 차량과 버스도 정지 또는 속도를 조절하고 있어 교통 사고의 위험은 낮아 보입니다.",
      "additional_notes": "하지만, 마스크 착용과 거리두기 등 코로나19 관련 안전 조치의 유무로 인해 사회적 거리두기 준수 여부를 확인할 수 없습니다."
    }
  ]
}
```
NATS publish 완료

종료 코드 0(으)로 완료된 프로세스
