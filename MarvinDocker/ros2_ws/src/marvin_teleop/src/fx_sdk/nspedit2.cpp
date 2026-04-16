// fx_sdk2.cpp : 此文件包含 "main" 函数。程序执行将在此处开始并结束。
//

#include <iostream>
#include "FxRobot.h"
#include "time.h"

void PNTPG(double m[4][4])
{
    printf("----PG---------------------------------------\n");
    for (long i = 0; i < 3; i++)
    {
        printf("%lf	%lf	%lf	%lf\n", m[i][0], m[i][1], m[i][2], m[i][3]);
    }

}

void PNTm77(double m[7][7])
{
    printf("----M77---------------------------------------\n");
    for (long i = 0; i < 7; i++)
    {
        for (long j = 0; j < 7; j++)

        {
            printf("%lf ", m[i][j]);
        }
        printf("\n");
    }


}



void PNTm88(double m[8][8])
{
    printf("----M88---------------------------------------\n");
    for (long i = 0; i < 8; i++)
    {
        for (long j = 0; j < 8; j++)

        {
            printf("%lf ", m[i][j]);
        }
        printf("\n");
    }


}

void PNTm67(double m[6][7])
{
    printf("----M67---------------------------------------\n");
    for (long i = 0; i < 6; i++)
    {
        for (long j = 0; j < 7; j++)

        {
            printf("%lf ", m[i][j]);
        }
        printf("\n");
    }


}


void PNV7(double v[7])
{
    for (long i = 0; i < 7; i++)
    {
        printf("%lf	", v[i]);
    }

    printf("\n");

}
double I[7][6];
double Mcp[7][3];
double Mass[7] = {11,12,13,14,15,16,17};

double PGB[7][4][4];
double PGA[7][4][4];

void InitPGB()
{
    long i, j, k;
    for (i = 0; i < 7; i++)
    {
        for (j = 0; j < 4; j++)
        {
            for (k = 0; k < 4; k++)
            {
                PGB[i][j][k] = 0;
                PGA[i][j][k] = 0;
            }
        }
        PGB[i][3][3] = 1;
        PGA[i][3][3] = 1;
    }
    PGB[0][0][0] = 1; PGB[0][1][1] = 1; PGB[0][2][2] = 1; PGB[0][2][3] = 174.5;
    PGB[1][0][0] = 1; PGB[1][2][1] = 1; PGB[1][1][2] = -1; PGB[1][2][3] = 174.5;
    PGB[2][0][0] = 1; PGB[2][1][1] = 1; PGB[2][2][2] = 1; PGB[2][2][3] = 461.5;
    PGB[3][0][0] = -1; PGB[3][2][1] = -1; PGB[3][1][2] = -1; PGB[3][2][3] = 461.5; PGB[3][0][3] = 18;
    PGB[4][0][0] = 1; PGB[4][1][1] = 1; PGB[4][2][2] = 1; PGB[4][2][3] = 775.5;
    PGB[5][0][1] = -1; PGB[5][1][2] = -1; PGB[5][2][0] = 1; PGB[5][2][3] = 775.5;
    PGB[6][0][2] = 1; PGB[6][1][0] = -1; PGB[6][2][1] = -1; PGB[6][2][3] = 775.5;
 
}


void MakePara()
{
    FX_INT32L TYPE[2];
    FX_DOUBLE GRV[2][3];
    FX_DOUBLE DH[2][8][4];
    FX_DOUBLE PNVA[2][7][4];
    FX_DOUBLE BD[2][4][3];

    FX_DOUBLE Mass[2][7];
    FX_DOUBLE MCP[2][7][3];
    FX_DOUBLE I[2][7][6];
    FX_BOOL ret = LOADMvCfg((char *)"D:\\TMP\\a.MvKDCfg", TYPE, GRV, DH, PNVA, BD, Mass, MCP, I);
    if (ret == FX_FALSE)
    {
        printf("LOAD ERR\n");
    }
    else
    {

        printf("LOAD OK\n");
    }
}

void TestJCB()
{
    FX_Robot_Init_Type(0, FX_ROBOT_TYPE_PILOT_CCS);
    FX_DOUBLE DH[8][4] =
    {
        0.000000,0.000000,174.5,0.000000,
        90.000000, 0.000000, 0.000000, 0.000000,
        -90.000000, 0.000000, 287.0000, 0.000000,
        90.000000, 18.000000, 0.000000, 180.000000,
        90.000000, 18.000000, 314.000000, -180.000000,
        90.000000, 0.000000, 0.000000, 90.000000,
        90.000000, 0.000000, 0.000000, 90.000000 ,
        90.000000,0.000000,88.000000,90.000000,
    };

    FX_Robot_Init_Kine(0, DH);
    FX_DOUBLE jv[7] = { 10,10,10,10,10,10,10 };
    FX_DOUBLE jvv[7] = { 10,10,10,10,10,10,10 };
    Matrix4 pg;
    FX_Robot_Kine_FK(0,jv,pg);
    PNTPG(pg);
    FX_Jacobi jcb, jcbd;
    FX_Robot_Kine_JacbJacbDot(0, jv, jvv, &jcb, &jcbd);

    PNTm67(jcb.m_Jcb);
    PNTm77(jcbd.m_Jcb);


}

void TestKine()
{
    InitPGB();
    FX_Robot_Init_Type(0, FX_ROBOT_TYPE_PILOT_CCS);
    FX_DOUBLE DH[8][4] =
    {
        0.000000,0.000000,174.5,0.000000,
        90.000000, 0.000000, 0.000000, 0.000000,
        -90.000000, 0.000000, 287.0000, 0.000000,
        90.000000, 18.000000, 0.000000, 180.000000,
        90.000000, 18.000000, 314.000000, -180.000000,
        90.000000, 0.000000, 0.000000, 90.000000,
        90.000000, 0.000000, 0.000000, 90.000000 ,
        90.000000,0.000000,88.000000,90.000000,
    };

    FX_Robot_Init_Kine(0, DH);
    FX_DOUBLE jv[7] = { 0,0,0,0,0,0,0 };
    FX_DOUBLE pg[4][4];

    double bmcp[3] = { 3,8,150 };

    double BI[3][3] = {
        1.1,0.1,0.1,
        0.1,1.2,0.1,
        0.1,0.1,1.3
    };

    for (long i = 0; i < 7; i++)
    {
        I[i][0] = BI[0][0]; I[i][1] = BI[0][1]; I[i][2] = BI[0][2];
        I[i][3] = BI[1][1]; I[i][4] = BI[1][2]; I[i][5] = BI[2][2];
        Mcp[i][0] = bmcp[0];
        Mcp[i][1] = bmcp[1];
        Mcp[i][2] = bmcp[2];
    }
    double grv[3] = { 0,0,9.81 };
    FX_Robot_Init_Dyna(0,grv, Mass, Mcp, I);

    Vect7 q = { 10,10,10,10,10,10,10 };
    Vect7 qd = { 10,10,10,10,10,10,10 };
    Vect7 qdd = { 10,10,10,10,10,10,10 };
    Vect6 ex_fn = { 0,0,0,0,0,0 };
    Vect7 ret_tau = { 0,0,0,0,0,0 };
    Matrix7 CTCC;
    clock_t t1, t2;
    t1 = clock();
    long tnum = 100;
    for (long ttt = 0; ttt < tnum; ttt++)
    {

        FX_Robot_Dyna_CalBase(0, q);
        Matrix7 ctbase;
        FX_Robot_Dyna_Centri_Base_Fix(0, ctbase);
        Matrix7 clbase[7];
        FX_Robot_Dyna_Coriolis_Base_Fix(0, clbase);

    }

    t2 = clock();
    double dt = t2 - t1;


    double sp = tnum;
    sp /= dt;

    printf("%lf \n", sp);
    {
        FX_Robot_Dyna_CalBase(0, q);
        FX_Robot_Dyna_ID_Fix(0, qd, qdd, ex_fn, ret_tau);
        Matrix7 mmat;
        FX_Robot_Dyna_MOI_Mat_Fix(0, mmat);
        Matrix7 ctbase;
        Matrix7 ctmat;
        FX_Robot_Dyna_Centri_Base_Fix(0, ctbase);
        FX_Robot_Dyna_Centri_Mat_Fix(0, ctbase, qd, ctmat);
        Matrix7 clbase[7];
        FX_Robot_Dyna_Coriolis_Base_Fix(0, clbase);
        Matrix7 colmat;
        FX_Robot_Dyna_Coriolis_Mat_Fix(0, clbase, qd, colmat);
        PNTm77(colmat);

        for (long i = 0; i < 7; i++)
        {
            for (long j = 0; j < 7; j++)
            {
                CTCC[i][j] = colmat[i][j] + ctmat[i][j];
            }
        }


    }
    PNTm77(CTCC);
}
#include "FXMatrix.h"
void TestDyn()
{
    FX_Robot_Init_Type(0, FX_ROBOT_TYPE_PILOT_CCS);
    FX_DOUBLE DH[8][4] =
    {
        0.000000,0.000000,174.5,0.000000,
        90.000000, 0.000000, 0.000000, 0.000000,
        -90.000000, 0.000000, 287.0000, 0.000000,
        90.000000, 18.000000, 0.000000, 180.000000,
        90.000000, 18.000000, 314.000000, -180.000000,
        90.000000, 0.000000, 0.000000, 90.000000,
        90.000000, 0.000000, 0.000000, 90.000000 ,
        90.000000,0.000000,88.000000,90.000000,
    };

    FX_Robot_Init_Kine(0, DH);
    FX_DOUBLE jv[7] = { 0,0,0,0,0,0,0 };
    FX_DOUBLE pg[4][4];
    FX_Robot_Kine_FK(0, jv, pg);


    double bmcp[3] = { 3,8,150 };

    double BI[3][3] = {
        1.1,0.1,0.1,
        0.1,1.2,0.1,
        0.1,0.1,1.3
    };

    for (long i = 0; i < 7; i++)
    {
        I[i][0] = BI[0][0]; I[i][1] = BI[0][1]; I[i][2] = BI[0][2];
        I[i][3] = BI[1][1]; I[i][4] = BI[1][2]; I[i][5] = BI[2][2];
        Mcp[i][0] = bmcp[0];
        Mcp[i][1] = bmcp[1];
        Mcp[i][2] = bmcp[2];
    }

    double grv[3] = { 0,0,9.81 };
    FX_Robot_Init_Dyna(0, grv, Mass, Mcp, I);

    Vect7 q = { 10,10,10,10,10,10,10 };
    Vect7 qd = { 10,10,10,10,10,10,10 };
    Vect7 qdd = { 10,10,10,10,10,10,10 };
    Vect6 ex_fn = { 0,0,0,0,0,0 };
    Vect7 ret_tau = { 0,0,0,0,0,0 };
    Matrix7 CTCC;


    {
        FX_Robot_Dyna_CalBase(0, q);
        FX_Robot_Dyna_ID_Fix(0, qd, qdd, ex_fn, ret_tau);
        Matrix7 mmat;
        FX_Robot_Dyna_MOI_Mat_Fix(0, mmat);
        Matrix7 ctbase;
        Matrix7 ctmat;
        FX_Robot_Dyna_Centri_Base_Fix(0, ctbase);
        FX_Robot_Dyna_Centri_Mat_Fix(0, ctbase, qd, ctmat);
        Matrix7 clbase[7];
        FX_Robot_Dyna_Coriolis_Base_Fix(0, clbase);
        Matrix7 colmat;
        FX_Robot_Dyna_Coriolis_Mat_Fix(0, clbase, qd, colmat);
        PNTm77(colmat);

        for (long i = 0; i < 7; i++)
        {
            for (long j = 0; j < 7; j++)
            {
                CTCC[i][j] = colmat[i][j] + ctmat[i][j];
            }
        }


    }

    double ges[3][3];
    FX_IdentM33(ges);
    double acc[3] = { 0 };
    double omg[3] = { 0,0,10.001};
    double omgd[3] = { 0,0,0.0 };

    FX_Robot_Dyna_Flt_BaseSet(0, ges, acc, omg, omgd);
    FX_Robot_Dyna_CalBase(0, q);

    Matrix8 clbase8[8];
    FX_Robot_Dyna_Coriolis_Base_Flt(0, clbase8);
    Matrix8 colmat8;
    FX_Robot_Dyna_Coriolis_Mat_Flt(0, clbase8, qd, colmat8);
    PNTm88(colmat8);

}
#include "FXMatrix.h"
void Test3()
{
    {
        Vect3 v1 = { 1,0,0 };
        Vect3 v2 = { 0,1,0 };
        Vect3 tmp;
        Matrix3 BI = {
              1.1,0.1,0.2,
              0.1,1.2,0.3,
              0.2,0.3,1.3
        };

        FX_MMV3(BI, v1, tmp);

        //   printf("%lf %lf %lf\n", tmp[0], tmp[1], tmp[2]);


        Vect3 rslt;
        FX_VectCross(v2, tmp, rslt);

        printf("%lf %lf %lf\n", rslt[0], rslt[1], rslt[2]);
    }

    {
        Vect3 v2 = { 1,0,0 };
        Vect3 v1 = { 0,1,0 };
        Vect3 tmp;
        Matrix3 BI = {
              1.1,0.1,0.2,
              0.1,1.2,0.3,
              0.2,0.3,1.3
        };

        FX_MMV3(BI, v1, tmp);

        //   printf("%lf %lf %lf\n", tmp[0], tmp[1], tmp[2]);


        Vect3 rslt;
        FX_VectCross(v2, tmp, rslt);

        printf("%lf %lf %lf\n", rslt[0], rslt[1], rslt[2]);
    }
    
}
// int main()
// {
//     TestDyn();
//     return 0;
//   //  TestJCB();
//   //  return 0;
//     TestKine();
//     std::cout << "Hello World!\n";
// }

// 运行程序: Ctrl + F5 或调试 >“开始执行(不调试)”菜单
// 调试程序: F5 或调试 >“开始调试”菜单

// 入门使用技巧: 
//   1. 使用解决方案资源管理器窗口添加/管理文件
//   2. 使用团队资源管理器窗口连接到源代码管理
//   3. 使用输出窗口查看生成输出和其他消息
//   4. 使用错误列表窗口查看错误
//   5. 转到“项目”>“添加新项”以创建新的代码文件，或转到“项目”>“添加现有项”以将现有代码文件添加到项目
//   6. 将来，若要再次打开此项目，请转到“文件”>“打开”>“项目”并选择 .sln 文件
